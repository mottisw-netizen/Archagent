using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace Archagent.Acad.Commands
{
    /// <summary>Distances between entities, from their real bounding boxes.</summary>
    internal static class DistanceCommand
    {
        public static Dictionary<string, object> Distance(Document doc, Dictionary<string, object> request)
        {
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var a = Box(tr, doc.Database, Json.String(request, "a", ""));
                var b = Box(tr, doc.Database, Json.String(request, "b", ""));
                string mode = Json.String(request, "mode", "clear");
                double value = mode == "centre" ? Centre(a).DistanceTo(Centre(b)) : ClearGap(a, b);
                tr.Commit();
                return new Dictionary<string, object>
                    { { "value", Units.Tidy(Units.ToMetres(doc.Database, value)) } };
            }
        }

        public static Dictionary<string, object> Overlap(Document doc, Dictionary<string, object> request)
        {
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var a = Box(tr, doc.Database, Json.String(request, "a", ""));
                var b = Box(tr, doc.Database, Json.String(request, "b", ""));
                double dx = Math.Min(a.MaxPoint.X, b.MaxPoint.X) - Math.Max(a.MinPoint.X, b.MinPoint.X);
                double dy = Math.Min(a.MaxPoint.Y, b.MaxPoint.Y) - Math.Max(a.MinPoint.Y, b.MinPoint.Y);
                double area = dx > 0 && dy > 0 ? Units.AreaToSquareMetres(doc.Database, dx * dy) : 0.0;
                tr.Commit();
                return new Dictionary<string, object>
                    { { "overlaps", area > 0 }, { "area", Units.Tidy(area) } };
            }
        }

        public static Dictionary<string, object> Clearance(Document doc, Dictionary<string, object> request)
        {
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var box = Box(tr, doc.Database, Json.String(request, "id", ""));
                double required = Json.Number(request, "required", 0.0);
                var gaps = new Dictionary<string, object>();
                double minimum = double.MaxValue;

                foreach (var other in Json.List(request, "against"))
                {
                    string id = Convert.ToString(other);
                    double gap = Units.ToMetres(doc.Database, ClearGap(box, Box(tr, doc.Database, id)));
                    gaps[id] = Units.Tidy(gap);
                    minimum = Math.Min(minimum, gap);
                }
                if (minimum == double.MaxValue) minimum = 0.0;
                tr.Commit();

                return new Dictionary<string, object>
                {
                    { "min", Units.Tidy(minimum) },
                    { "passes", minimum >= required },
                    { "gaps", gaps },
                };
            }
        }

        private static Extents3d Box(Transaction tr, Database db, string handleHex)
        {
            var entity = QueryCommands.Resolve(tr, db, handleHex);
            if (!entity.Bounds.HasValue)
                throw new HostException(Protocol.ErrMeasurement,
                    "element " + handleHex + " has no geometry");
            return entity.Bounds.Value;
        }

        private static Point3d Centre(Extents3d box) =>
            new Point3d((box.MinPoint.X + box.MaxPoint.X) / 2.0,
                       (box.MinPoint.Y + box.MaxPoint.Y) / 2.0,
                       (box.MinPoint.Z + box.MaxPoint.Z) / 2.0);

        private static double ClearGap(Extents3d a, Extents3d b)
        {
            double dx = Math.Max(Math.Max(a.MinPoint.X - b.MaxPoint.X, b.MinPoint.X - a.MaxPoint.X), 0.0);
            double dy = Math.Max(Math.Max(a.MinPoint.Y - b.MaxPoint.Y, b.MinPoint.Y - a.MaxPoint.Y), 0.0);
            return Math.Sqrt(dx * dx + dy * dy);
        }
    }
}
