using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace Archagent.Acad
{
    /// <summary>
    /// Turns an AutoCAD entity into the document the protocol describes.
    ///
    /// Revit elements arrive typed (a family, a category) out of the box; a
    /// plain AutoCAD entity does not. Two conventions carry that information,
    /// checked in order, and both are documented in README.md because a
    /// consultant's drawing has to follow one of them to participate at all:
    ///
    /// 1. XDATA under the registered application "ARCHAGENT" - a JSON string
    ///    (category, label, level, sheet, properties) written by Archagent
    ///    itself once a plan has touched the entity, or by whoever tags the
    ///    drawing for Archagent to work with;
    /// 2. failing that, the entity's **layer name**, matched against the same
    ///    AIA-style prefixes the reference JSON model uses (A-PARK, A-BLDG,
    ///    A-ROAD, ...) - the layer convention most DWGs already follow.
    ///
    /// Two decisions matter, same as the Revit add-in:
    /// * the id on the wire is <see cref="Handle"/> as a hex string, because an
    ///   <see cref="ObjectId"/> is only valid for the session that created it;
    /// * geometry is the plan bounding box in metres, project coordinates,
    ///   +x east and +y north - the frame the planner and the previews assume.
    /// </summary>
    internal static class EntityView
    {
        public const string AppName = "ARCHAGENT";

        //: Layer-name keyword -> the vocabulary the planner reasons about.
        //: Checked as a substring of the layer name, so "A-PARK-VISITOR"
        //: matches "PARK" -> parking.
        //:
        //: ORDER IS SIGNIFICANT - the first keyword found in the layer name
        //: wins, so every specific keyword must precede any more general one
        //: that could appear in the same layer name ("C-ROAD-CURB" has to be
        //: curb, not the driveway a leading "ROAD" entry would give it).
        //: Kept in the same order as
        //: archagent.drawing.dxf_model.LAYER_CATEGORIES (Python), so a
        //: drawing categorises identically live and headlessly.
        private static readonly (string Keyword, string Category)[] LayerCategories =
        {
            // --- specific first (roads/drainage/landscape) ---
            ("MUNI", "municipal_drain"), ("CHAMBER", "drainage_chamber"),
            ("MANHOLE", "catch_basin"), ("DRAIN", "drainage_pipe"),
            ("CURB", "curb"), ("RAMP", "ramp"), ("TREE", "tree"),
            ("PLNT", "landscape_zone"), ("PLANT", "landscape_zone"),
            // --- then the general architectural vocabulary ---
            ("PARK", "parking"), ("PARKING", "parking"),
            ("BLDG", "building"), ("BUILDING", "building"),
            ("WALL", "wall"),
            ("ROOM", "room"),
            ("DOOR", "door"),
            ("WIND", "window"),
            ("STAIR", "stair"),
            ("RAIL", "railing"),
            ("FLOOR", "floor"),
            ("ROOF", "roof"),
            ("COL", "column"),
            ("ROAD", "driveway"), ("DRIVE", "driveway"),
            ("WALK", "sidewalk"), ("SIDEWALK", "sidewalk"),
            ("DIM", "dimension"),
            ("TEXT", "text"), ("ANNO", "text"),
            ("SITE", "site"), ("PROP", "site"),
        };

        public static string CategoryOf(Entity entity)
        {
            var tagged = ReadTag(entity);
            if (tagged != null && tagged.TryGetValue("category", out var value)
                && !string.IsNullOrWhiteSpace(Convert.ToString(value)))
                return Convert.ToString(value);

            if (entity is Dimension) return "dimension";
            if (entity is DBText || entity is MText) return "text";

            string layer = (entity.Layer ?? string.Empty).ToUpperInvariant();
            foreach (var pair in LayerCategories)
                if (layer.Contains(pair.Keyword)) return pair.Category;
            return "generic";
        }

        public static Dictionary<string, object> Describe(Transaction tr, Database db, Entity entity)
        {
            var box = BoxOf(db, entity.Bounds);
            var tagged = ReadTag(entity) ?? new Dictionary<string, object>();
            var geometry = new Dictionary<string, object>
            {
                { "bbox", box },
                { "elevation", entity.Bounds.HasValue
                    ? Units.Tidy(Units.ToMetres(db, entity.Bounds.Value.MinPoint.Z)) : 0.0 },
                { "height", entity.Bounds.HasValue
                    ? Units.Tidy(Units.ToMetres(db, entity.Bounds.Value.MaxPoint.Z - entity.Bounds.Value.MinPoint.Z))
                    : 0.0 },
                { "rotation", RotationOf(entity) },
            };

            return new Dictionary<string, object>
            {
                { "id", entity.Handle.ToString() },
                { "category", CategoryOf(entity) },
                { "type_name", entity.GetType().Name },
                { "name", Json.String(tagged, "name", string.Empty) },
                { "label", MarkOf(entity, tagged) },
                { "level", Json.String(tagged, "level", string.Empty) },
                { "sheet", Json.String(tagged, "sheet", string.Empty) },
                { "geometry", geometry },
                { "properties", Properties(db, entity, tagged) },
                { "editable", true },
                { "pinned", false },
                { "workset", string.Empty },
            };
        }

        public static Dictionary<string, object> BoxOf(Database db, Extents3d? bounds)
        {
            if (!bounds.HasValue)
                return new Dictionary<string, object>
                    { { "x", 0.0 }, { "y", 0.0 }, { "w", 0.0 }, { "h", 0.0 } };

            var extents = bounds.Value;
            double x = Units.ToMetres(db, extents.MinPoint.X);
            double y = Units.ToMetres(db, extents.MinPoint.Y);
            double w = Units.ToMetres(db, extents.MaxPoint.X - extents.MinPoint.X);
            double h = Units.ToMetres(db, extents.MaxPoint.Y - extents.MinPoint.Y);
            return new Dictionary<string, object>
            {
                { "x", Units.Tidy(x) }, { "y", Units.Tidy(y) },
                { "w", Units.Tidy(w) }, { "h", Units.Tidy(h) },
            };
        }

        public static string MarkOf(Entity entity, Dictionary<string, object> tagged)
        {
            string label = Json.String(tagged, "label", string.Empty);
            if (!string.IsNullOrWhiteSpace(label)) return label;
            if (entity is DBText text) return text.TextString;
            if (entity is MText mtext) return mtext.Text;
            return entity.Handle.ToString();
        }

        public static double RotationOf(Entity entity)
        {
            switch (entity)
            {
                case BlockReference block: return Math.Round(block.Rotation * 180.0 / Math.PI, 6);
                case Polyline polyline when polyline.NumberOfVertices >= 2:
                {
                    var a = polyline.GetPoint2dAt(0);
                    var b = polyline.GetPoint2dAt(1);
                    return Math.Round(Math.Atan2(b.Y - a.Y, b.X - a.X) * 180.0 / Math.PI, 6);
                }
                default: return 0.0;
            }
        }

        /// <summary>
        /// Which plan axis the entity's own "width" runs along - the same
        /// convention the JSON reference driver and the Revit add-in use, so a
        /// resize anchored "south_west" means the same thing everywhere.
        /// A rectangular polyline reports its longer run as "length", the
        /// shorter as "width", along whichever axis it actually measures larger.
        /// </summary>
        public static string WidthAxisOf(Database db, Entity entity)
        {
            var box = entity.Bounds;
            if (!box.HasValue) return "x";
            double w = Units.ToMetres(db, box.Value.MaxPoint.X - box.Value.MinPoint.X);
            double h = Units.ToMetres(db, box.Value.MaxPoint.Y - box.Value.MinPoint.Y);
            return w <= h ? "x" : "y";
        }

        // ------------------------------------------------------------------
        // XDATA: how Archagent tags an entity with what a family/parameter
        // would tell it in Revit. Read as one JSON blob under a single field
        // so tagging an entity is one AppendInfoName + one string, not a
        // schema of registered fields.
        // ------------------------------------------------------------------
        public static Dictionary<string, object> ReadTag(Entity entity)
        {
            var data = entity.GetXDataForApplication(AppName);
            if (data == null) return null;
            foreach (TypedValue value in data)
                if (value.TypeCode == (int)DxfCode.ExtendedDataAsciiString)
                    return Json.Read(Convert.ToString(value.Value));
            return null;
        }

        public static void WriteTag(Transaction tr, Database db, Entity entity, Dictionary<string, object> tag)
        {
            EnsureRegistered(tr, db);
            entity.UpgradeOpen();
            var data = new ResultBuffer(
                new TypedValue((int)DxfCode.ExtendedDataRegAppName, AppName),
                new TypedValue((int)DxfCode.ExtendedDataAsciiString, Json.Write(tag)));
            entity.XData = data;
        }

        private static void EnsureRegistered(Transaction tr, Database db)
        {
            var table = (RegAppTable)tr.GetObject(db.RegAppTableId, OpenMode.ForRead);
            if (table.Has(AppName)) return;
            table.UpgradeOpen();
            var record = new RegAppTableRecord { Name = AppName };
            table.Add(record);
            tr.AddNewlyCreatedDBObject(record, true);
        }

        public static Dictionary<string, object> Properties(
            Database db, Entity entity, Dictionary<string, object> tagged)
        {
            var values = new Dictionary<string, object>();
            if (tagged != null && tagged.TryGetValue("properties", out var raw)
                && raw is Dictionary<string, object> nested)
                foreach (var pair in nested) values[pair.Key] = pair.Value;
            values["width_axis"] = WidthAxisOf(db, entity);
            values["layer"] = entity.Layer ?? string.Empty;
            return values;
        }

        public static IEnumerable<Entity> Collect(Transaction tr, Database db, string category)
        {
            var space = (BlockTableRecord)tr.GetObject(
                SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
            foreach (ObjectId id in space)
            {
                if (!(tr.GetObject(id, OpenMode.ForRead) is Entity entity)) continue;
                if (!string.IsNullOrWhiteSpace(category) && CategoryOf(entity) != category) continue;
                yield return entity;
            }
        }
    }
}
