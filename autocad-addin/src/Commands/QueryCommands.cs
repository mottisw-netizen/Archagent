using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;

namespace Archagent.Acad.Commands
{
    /// <summary>Everything the agent reads: entities, geometry, sheets (layouts), measurements.</summary>
    internal static class QueryCommands
    {
        public static Dictionary<string, object> Health(Document doc)
        {
            int count = 0;
            if (doc != null)
            {
                using (var tr = doc.Database.TransactionManager.StartTransaction())
                {
                    count = EntityView.Collect(tr, doc.Database, null).Count();
                    tr.Commit();
                }
            }
            return new Dictionary<string, object>
            {
                { "protocol", Protocol.Version },
                { "host", "autocad" },
                { "host_version", Autodesk.AutoCAD.ApplicationServices.Core.Application.Version.ToString() },
                { "document", doc?.Name ?? string.Empty },
                { "units", "m" },
                { "read_only", doc != null && doc.IsReadOnly },
                { "project_north", 0.0 },
                { "element_count", count },
            };
        }

        public static Dictionary<string, object> Find(Document doc, Dictionary<string, object> request)
        {
            var filter = Json.Dict(request, "filter");
            bool full = Json.String(request, "detail", "") == "full";
            string category = Json.String(filter, "type", Json.String(filter, "category", ""));

            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var matches = EntityView.Collect(tr, doc.Database, category)
                    .Where(entity => Matches(doc.Database, entity, filter))
                    .ToList();
                var result = !full
                    ? new Dictionary<string, object>
                        { { "elements", matches.Select(e => (object)e.Handle.ToString()).ToList() } }
                    : new Dictionary<string, object>
                        { { "elements", matches.Select(e => (object)EntityView.Describe(tr, doc.Database, e)).ToList() } };
                tr.Commit();
                return result;
            }
        }

        private static bool Matches(Database db, Entity entity, Dictionary<string, object> filter)
        {
            var tagged = EntityView.ReadTag(entity) ?? new Dictionary<string, object>();
            foreach (var pair in filter)
            {
                string expected = Convert.ToString(pair.Value) ?? string.Empty;
                string actual;
                switch (pair.Key)
                {
                    case "type":
                    case "category":
                        actual = EntityView.CategoryOf(entity);
                        break;
                    case "id":
                    case "element_id":
                        actual = entity.Handle.ToString();
                        break;
                    case "label":
                        actual = EntityView.MarkOf(entity, tagged);
                        break;
                    case "label_contains":
                        if (!EntityView.MarkOf(entity, tagged).ToLowerInvariant()
                                .Contains(expected.ToLowerInvariant()))
                            return false;
                        continue;
                    case "level":
                        actual = Json.String(tagged, "level", string.Empty);
                        break;
                    default:
                        actual = tagged.TryGetValue(pair.Key, out var value)
                            ? Convert.ToString(value) : string.Empty;
                        break;
                }
                if (!string.Equals(actual ?? string.Empty, expected,
                        StringComparison.OrdinalIgnoreCase))
                    return false;
            }
            return true;
        }

        public static Dictionary<string, object> Element(Document doc, Dictionary<string, object> request)
        {
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var entity = Resolve(tr, doc.Database, Json.String(request, "id", ""));
                var described = EntityView.Describe(tr, doc.Database, entity);
                tr.Commit();
                return described;
            }
        }

        public static Dictionary<string, object> Geometry(Document doc, Dictionary<string, object> request)
        {
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var entity = Resolve(tr, doc.Database, Json.String(request, "id", ""));
                var box = EntityView.BoxOf(doc.Database, entity.Bounds);
                var result = new Dictionary<string, object>
                {
                    { "bbox", box },
                    { "area", Units.Tidy(Convert.ToDouble(box["w"]) * Convert.ToDouble(box["h"])) },
                    { "width", box["w"] },
                    { "length", box["h"] },
                    { "level", string.Empty },
                };
                tr.Commit();
                return result;
            }
        }

        public static Dictionary<string, object> Properties(Document doc, Dictionary<string, object> request)
        {
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var entity = Resolve(tr, doc.Database, Json.String(request, "id", ""));
                var tagged = EntityView.ReadTag(entity);
                var result = new Dictionary<string, object>
                    { { "properties", EntityView.Properties(doc.Database, entity, tagged) } };
                tr.Commit();
                return result;
            }
        }

        /// <summary>
        /// AutoCAD's "sheets" are layouts; its closest thing to a schedule is a
        /// <see cref="Table"/> entity, tagged the same way an element is.
        /// </summary>
        public static Dictionary<string, object> Sheets(Document doc)
        {
            var sheets = new List<object>();
            var schedules = new Dictionary<string, object>();
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var layouts = (DBDictionary)tr.GetObject(doc.Database.LayoutDictionaryId, OpenMode.ForRead);
                foreach (var entry in layouts)
                {
                    if (entry.Key == "Model") continue;
                    var layout = (Layout)tr.GetObject(entry.Value, OpenMode.ForRead);
                    sheets.Add(new Dictionary<string, object>
                        { { "id", entry.Key }, { "name", layout.LayoutName } });
                }
                foreach (var entity in EntityView.Collect(tr, doc.Database, null))
                {
                    if (!(entity is Table table)) continue;
                    schedules[table.Handle.ToString()] = new Dictionary<string, object>
                    {
                        { "title", EntityView.MarkOf(table, EntityView.ReadTag(table)) },
                        { "unique_id", table.Handle.ToString() },
                        { "rows", table.Rows.Count },
                        { "columns", table.Columns.Count },
                    };
                }
                tr.Commit();
            }
            return new Dictionary<string, object> { { "sheets", sheets }, { "schedules", schedules } };
        }

        public static Entity Resolve(Transaction tr, Database db, string handleHex)
        {
            try
            {
                var handle = new Handle(Convert.ToInt64(handleHex, 16));
                if (db.TryGetObjectId(handle, out ObjectId id))
                    return tr.GetObject(id, OpenMode.ForRead) as Entity
                        ?? throw HostException.NotFound(handleHex);
            }
            catch (FormatException) { /* fall through to NotFound below */ }
            catch (OverflowException) { /* fall through to NotFound below */ }
            throw HostException.NotFound(handleHex);
        }
    }
}
