using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;

namespace Archagent.Revit
{
    /// <summary>
    /// Turns a Revit element into the document the protocol describes.
    ///
    /// Two decisions matter here and are deliberate:
    /// * the id on the wire is <see cref="Element.UniqueId"/>, because ElementId
    ///   is not stable across sessions and the agent stores ids in reports;
    /// * the geometry is the plan bounding box in metres, in project
    ///   coordinates with +x east and +y north, which is the frame the planner
    ///   and the previews assume.
    /// </summary>
    internal static class ElementView
    {
        /// <summary>Revit category -> the vocabulary the planner reasons about.</summary>
        private static readonly Dictionary<BuiltInCategory, string> CategoryNames =
            new Dictionary<BuiltInCategory, string>
            {
                { BuiltInCategory.OST_Parking, "parking" },
                { BuiltInCategory.OST_Walls, "wall" },
                { BuiltInCategory.OST_Rooms, "room" },
                { BuiltInCategory.OST_Doors, "door" },
                { BuiltInCategory.OST_Windows, "window" },
                { BuiltInCategory.OST_Floors, "floor" },
                { BuiltInCategory.OST_Roofs, "roof" },
                { BuiltInCategory.OST_Stairs, "stair" },
                { BuiltInCategory.OST_StairsRailing, "railing" },
                { BuiltInCategory.OST_Columns, "column" },
                { BuiltInCategory.OST_StructuralColumns, "column" },
                { BuiltInCategory.OST_Mass, "building" },
                { BuiltInCategory.OST_Roads, "driveway" },
                { BuiltInCategory.OST_Site, "site" },
                { BuiltInCategory.OST_Topography, "site" },
                { BuiltInCategory.OST_Dimensions, "dimension" },
                { BuiltInCategory.OST_TextNotes, "text" },
                { BuiltInCategory.OST_GenericModel, "generic" },
                { BuiltInCategory.OST_Sheets, "sheet" },
            };

        public static string CategoryOf(Element element)
        {
            var category = element?.Category;
            if (category == null) return "generic";
            var builtIn = (BuiltInCategory)category.Id.IntegerValue;
            return CategoryNames.TryGetValue(builtIn, out var name)
                ? name
                : category.Name.ToLowerInvariant();
        }

        public static Dictionary<string, object> Describe(Document doc, Element element)
        {
            var bbox = element.get_BoundingBox(null);
            var geometry = new Dictionary<string, object>
            {
                { "bbox", BoxOf(bbox) },
                { "elevation", bbox == null ? 0.0 : Units.Tidy(Units.ToMetres(bbox.Min.Z)) },
                { "height", bbox == null ? 0.0 : Units.Tidy(Units.ToMetres(bbox.Max.Z - bbox.Min.Z)) },
                { "rotation", RotationOf(element) },
            };

            return new Dictionary<string, object>
            {
                { "id", element.UniqueId },
                { "category", CategoryOf(element) },
                { "type_name", TypeNameOf(doc, element) },
                { "name", element.Name ?? string.Empty },
                { "label", MarkOf(element) },
                { "level", LevelOf(doc, element) },
                { "sheet", string.Empty },
                { "geometry", geometry },
                { "properties", Parameters(element) },
                { "editable", !element.Pinned },
                { "pinned", element.Pinned },
                { "workset", WorksetOf(doc, element) },
            };
        }

        public static Dictionary<string, object> BoxOf(BoundingBoxXYZ bbox)
        {
            if (bbox == null)
                return new Dictionary<string, object>
                    { { "x", 0.0 }, { "y", 0.0 }, { "w", 0.0 }, { "h", 0.0 } };

            double x = Units.ToMetres(bbox.Min.X);
            double y = Units.ToMetres(bbox.Min.Y);
            double w = Units.ToMetres(bbox.Max.X - bbox.Min.X);
            double h = Units.ToMetres(bbox.Max.Y - bbox.Min.Y);
            return new Dictionary<string, object>
            {
                { "x", Units.Tidy(x) }, { "y", Units.Tidy(y) },
                { "w", Units.Tidy(w) }, { "h", Units.Tidy(h) },
            };
        }

        public static string MarkOf(Element element)
        {
            var mark = element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK);
            var value = mark?.AsString();
            if (!string.IsNullOrWhiteSpace(value)) return value;

            var number = element.get_Parameter(BuiltInParameter.ROOM_NUMBER);
            value = number?.AsString();
            return string.IsNullOrWhiteSpace(value) ? (element.Name ?? string.Empty) : value;
        }

        public static string LevelOf(Document doc, Element element)
        {
            if (element.LevelId != null && element.LevelId != ElementId.InvalidElementId)
                return doc.GetElement(element.LevelId)?.Name ?? string.Empty;
            var parameter = element.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM);
            if (parameter != null && parameter.StorageType == StorageType.ElementId)
                return doc.GetElement(parameter.AsElementId())?.Name ?? string.Empty;
            return string.Empty;
        }

        private static string TypeNameOf(Document doc, Element element)
        {
            var typeId = element.GetTypeId();
            if (typeId == null || typeId == ElementId.InvalidElementId) return string.Empty;
            return doc.GetElement(typeId)?.Name ?? string.Empty;
        }

        private static string WorksetOf(Document doc, Element element)
        {
            if (!doc.IsWorkshared) return string.Empty;
            var table = doc.GetWorksetTable();
            var workset = table.GetWorkset(element.WorksetId);
            return workset?.Name ?? string.Empty;
        }

        public static double RotationOf(Element element)
        {
            if (element.Location is LocationPoint point)
                return Math.Round(point.Rotation * 180.0 / Math.PI, 6);
            return 0.0;
        }

        /// <summary>
        /// Instance and type parameters, as strings and numbers. Lengths are
        /// converted to metres so the agent never sees feet.
        /// </summary>
        public static Dictionary<string, object> Parameters(Element element)
        {
            var values = new Dictionary<string, object>();
            foreach (Parameter parameter in element.Parameters)
            {
                if (parameter?.Definition == null) continue;
                var name = parameter.Definition.Name;
                if (values.ContainsKey(name)) continue;

                switch (parameter.StorageType)
                {
                    case StorageType.Double:
                        values[name] = Units.Tidy(ConvertDouble(parameter));
                        break;
                    case StorageType.Integer:
                        values[name] = parameter.AsInteger();
                        break;
                    case StorageType.String:
                        values[name] = parameter.AsString() ?? string.Empty;
                        break;
                    case StorageType.ElementId:
                        values[name] = parameter.AsValueString() ?? string.Empty;
                        break;
                }
            }
            values["width_axis"] = WidthAxisOf(element);
            return values;
        }

        private static double ConvertDouble(Parameter parameter)
        {
            double raw = parameter.AsDouble();
            try
            {
                var typeId = parameter.GetUnitTypeId();
                if (typeId != null && typeId.Equals(UnitTypeId.Feet))
                    return Units.ToMetres(raw);
                if (typeId != null && typeId.Equals(UnitTypeId.SquareFeet))
                    return Units.AreaToSquareMetres(raw);
            }
            catch (Exception)
            {
                // Older parameters may not expose a unit; fall through to raw.
            }
            return raw;
        }

        /// <summary>
        /// Which plan axis the element's own "width" runs along. A rotated
        /// family reports its facing; anything else is measured on x.
        /// </summary>
        public static string WidthAxisOf(Element element)
        {
            if (element is FamilyInstance instance)
            {
                var facing = instance.FacingOrientation;
                if (facing != null && Math.Abs(facing.Y) > Math.Abs(facing.X))
                    return "x";     // facing north/south -> width runs east-west
                if (facing != null) return "y";
            }
            return "x";
        }

        public static IEnumerable<Element> Collect(Document doc, string category)
        {
            var collector = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType();
            if (!string.IsNullOrWhiteSpace(category))
            {
                var builtIn = CategoryNames.FirstOrDefault(pair => pair.Value == category).Key;
                if (builtIn != default(BuiltInCategory))
                    collector = collector.OfCategory(builtIn);
            }
            return collector.Where(element => element.Category != null);
        }
    }
}
