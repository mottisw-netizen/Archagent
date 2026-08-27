using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;

namespace Archagent.Acad.Commands
{
    /// <summary>
    /// Measurement, from the drawing's own geometry.
    ///
    /// Same rule as the Revit host: a number in a report came from a
    /// measurement tool, which here means reading it from the entity's
    /// geometry or its Archagent tag. What this host cannot measure it says so
    /// about - <c>unsupported</c> - rather than inventing a number.
    /// </summary>
    internal static class MeasureCommand
    {
        public static Dictionary<string, object> Run(Document doc, Dictionary<string, object> request)
        {
            var subject = Json.Dict(request, "subject");
            string metric = Json.String(request, "metric", "");
            string basis = Json.String(request, "basis", "clear");

            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                Dictionary<string, object> result;
                switch (metric)
                {
                    case "width":
                    case "length":
                    case "height":
                        result = Dimension(tr, doc.Database, subject, metric, basis);
                        break;
                    case "area":
                        result = Area(tr, doc.Database, subject, basis);
                        break;
                    case "count":
                        result = Count(tr, doc.Database, subject);
                        break;
                    case "setback":
                        result = Setback(tr, doc.Database, subject);
                        break;
                    case "floor_area":
                        result = FloorArea(tr, doc.Database, basis);
                        break;
                    default:
                        // clear_width and clear_distance are relationships between
                        // entities: the agent computes those from the boxes it
                        // already has, and the answer is identical.
                        throw HostException.Unsupported("this host does not measure " + metric);
                }
                tr.Commit();
                return result;
            }
        }

        private static Entity Single(Transaction tr, Database db, Dictionary<string, object> subject)
        {
            string id = Json.String(subject, "element_id", "");
            if (!string.IsNullOrEmpty(id)) return QueryCommands.Resolve(tr, db, id);

            var selector = Json.Dict(subject, "selector");
            var matches = EntityView.Collect(tr, db, Json.String(selector, "type", ""))
                .Where(e => MatchesSelector(db, e, selector)).ToList();
            if (matches.Count == 0) throw HostException.NotFound(Json.Describe(selector));
            if (matches.Count > 1)
                throw new HostException(Protocol.ErrAmbiguous,
                    "subject matches " + matches.Count + " elements",
                    matches.Select(e => (object)e.Handle.ToString()).ToArray());
            return matches[0];
        }

        private static bool MatchesSelector(Database db, Entity entity, Dictionary<string, object> selector)
        {
            var tagged = EntityView.ReadTag(entity) ?? new Dictionary<string, object>();
            if (selector.TryGetValue("label", out var label) &&
                !string.Equals(EntityView.MarkOf(entity, tagged), Convert.ToString(label),
                    StringComparison.OrdinalIgnoreCase))
                return false;
            return true;
        }

        private static Dictionary<string, object> Dimension(
            Transaction tr, Database db, Dictionary<string, object> subject, string metric, string basis)
        {
            var entity = Single(tr, db, subject);
            var box = entity.Bounds;
            if (!box.HasValue) throw new HostException(Protocol.ErrMeasurement, "no geometry");

            double w = Units.ToMetres(db, box.Value.MaxPoint.X - box.Value.MinPoint.X);
            double h = Units.ToMetres(db, box.Value.MaxPoint.Y - box.Value.MinPoint.Y);
            double z = Units.ToMetres(db, box.Value.MaxPoint.Z - box.Value.MinPoint.Z);
            string axis = EntityView.WidthAxisOf(db, entity);
            double value = metric == "height" ? z
                : metric == "width" ? (axis == "x" ? w : h)
                : (axis == "x" ? h : w);
            return Result(Units.Tidy(value), "m", basis, "bounding_box");
        }

        private static Dictionary<string, object> Area(
            Transaction tr, Database db, Dictionary<string, object> subject, string basis)
        {
            var entity = Single(tr, db, subject);
            if (entity is Polyline polyline && polyline.Closed)
                return Result(Units.Tidy(Units.AreaToSquareMetres(db, Math.Abs(polyline.Area))),
                    "m2", basis, "polyline_area");

            var box = entity.Bounds;
            if (!box.HasValue) throw new HostException(Protocol.ErrMeasurement, "no geometry");
            double area = Units.ToMetres(db, box.Value.MaxPoint.X - box.Value.MinPoint.X) *
                          Units.ToMetres(db, box.Value.MaxPoint.Y - box.Value.MinPoint.Y);
            return Result(Units.Tidy(area), "m2", basis, "bounding_box");
        }

        private static Dictionary<string, object> Count(
            Transaction tr, Database db, Dictionary<string, object> subject)
        {
            var selector = Json.Dict(subject, "selector");
            int count = EntityView.Collect(tr, db, Json.String(selector, "type", ""))
                .Count(e => MatchesSelector(db, e, selector));
            return Result(count, "count", "clear", "find_element");
        }

        /// <summary>
        /// Distance from an entity's edge to the property line - an entity on
        /// a layer matched by "SITE"/"PROP" (see <c>EntityView.LayerCategories</c>).
        /// Without one in the drawing there is nothing to measure against.
        /// </summary>
        private static Dictionary<string, object> Setback(
            Transaction tr, Database db, Dictionary<string, object> subject)
        {
            string edge = Json.String(subject, "edge", "");
            if (string.IsNullOrEmpty(edge))
                throw new HostException(Protocol.ErrMeasurement, "a setback needs an edge");

            var entity = Single(tr, db, subject);
            var box = entity.Bounds;
            if (!box.HasValue) throw new HostException(Protocol.ErrMeasurement, "no geometry");

            var plotEntity = EntityView.Collect(tr, db, "site").FirstOrDefault();
            if (plotEntity?.Bounds == null)
                throw HostException.Unsupported(
                    "the drawing has no property line (a 'site' entity), so a setback cannot be measured here");
            var plot = plotEntity.Bounds.Value;

            double value;
            switch (edge)
            {
                case "north": value = Units.ToMetres(db, plot.MaxPoint.Y - box.Value.MaxPoint.Y); break;
                case "south": value = Units.ToMetres(db, box.Value.MinPoint.Y - plot.MinPoint.Y); break;
                case "east": value = Units.ToMetres(db, plot.MaxPoint.X - box.Value.MaxPoint.X); break;
                case "west": value = Units.ToMetres(db, box.Value.MinPoint.X - plot.MinPoint.X); break;
                default: throw HostException.Unsupported("unknown edge: " + edge);
            }
            return Result(Units.Tidy(value), "m", "to plot line", "property_line");
        }

        private static Dictionary<string, object> FloorArea(Transaction tr, Database db, string basis)
        {
            double total = 0.0;
            foreach (var entity in EntityView.Collect(tr, db, "building"))
                if (entity is Polyline polyline && polyline.Closed)
                    total += Units.AreaToSquareMetres(db, Math.Abs(polyline.Area));
            if (total <= 0.0)
                throw HostException.Unsupported(
                    "no closed 'building' polyline found, so built floor area cannot be measured here");
            return Result(Units.Tidy(total), "m2", basis, "polyline_area");
        }

        private static Dictionary<string, object> Result(
            object value, string unit, string basis, string tool)
        {
            return new Dictionary<string, object>
            {
                { "value", value }, { "unit", unit }, { "basis", basis },
                { "tool", "autocad:" + tool },
                { "details", new Dictionary<string, object>() },
            };
        }
    }
}
