using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace Archagent.Revit.Commands
{
    /// <summary>Distances between elements, from their real bounding boxes.</summary>
    internal static class DistanceCommand
    {
        public static Dictionary<string, object> Distance(
            Document doc, Dictionary<string, object> request)
        {
            var a = Box(doc, Json.String(request, "a", ""));
            var b = Box(doc, Json.String(request, "b", ""));
            string mode = Json.String(request, "mode", "clear");

            double value = mode == "centre"
                ? Centre(a).DistanceTo(Centre(b))
                : ClearGap(a, b);
            return new Dictionary<string, object> { { "value", Units.Tidy(Units.ToMetres(value)) } };
        }

        public static Dictionary<string, object> Overlap(
            Document doc, Dictionary<string, object> request)
        {
            var a = Box(doc, Json.String(request, "a", ""));
            var b = Box(doc, Json.String(request, "b", ""));
            double dx = Math.Min(a.Max.X, b.Max.X) - Math.Max(a.Min.X, b.Min.X);
            double dy = Math.Min(a.Max.Y, b.Max.Y) - Math.Max(a.Min.Y, b.Min.Y);
            double area = dx > 0 && dy > 0
                ? Units.AreaToSquareMetres(dx * dy)
                : 0.0;
            return new Dictionary<string, object>
                { { "overlaps", area > 0 }, { "area", Units.Tidy(area) } };
        }

        public static Dictionary<string, object> Clearance(
            Document doc, Dictionary<string, object> request)
        {
            var box = Box(doc, Json.String(request, "id", ""));
            double required = Json.Number(request, "required", 0.0);
            var gaps = new Dictionary<string, object>();
            double minimum = double.MaxValue;

            foreach (var other in Json.List(request, "against"))
            {
                string id = Convert.ToString(other);
                double gap = Units.ToMetres(ClearGap(box, Box(doc, id)));
                gaps[id] = Units.Tidy(gap);
                minimum = Math.Min(minimum, gap);
            }
            if (minimum == double.MaxValue) minimum = 0.0;

            return new Dictionary<string, object>
            {
                { "min", Units.Tidy(minimum) },
                { "passes", minimum >= required },
                { "gaps", gaps },
            };
        }

        private static BoundingBoxXYZ Box(Document doc, string uniqueId)
        {
            var element = QueryCommands.Resolve(doc, uniqueId);
            var bbox = element.get_BoundingBox(null);
            if (bbox == null)
                throw new HostException(Protocol.ErrMeasurement,
                    "element " + uniqueId + " has no geometry");
            return bbox;
        }

        private static XYZ Centre(BoundingBoxXYZ box) => (box.Min + box.Max) * 0.5;

        private static double ClearGap(BoundingBoxXYZ a, BoundingBoxXYZ b)
        {
            double dx = Math.Max(Math.Max(a.Min.X - b.Max.X, b.Min.X - a.Max.X), 0.0);
            double dy = Math.Max(Math.Max(a.Min.Y - b.Max.Y, b.Min.Y - a.Max.Y), 0.0);
            return Math.Sqrt(dx * dx + dy * dy);
        }
    }
}
