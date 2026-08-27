using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace Archagent.Acad.Commands
{
    /// <summary>
    /// Applies a whole correction plan in one transaction.
    ///
    /// This is the only place in the add-in that writes. Unlike the Revit
    /// host, one AutoCAD <see cref="Transaction"/> already is one undo step, so
    /// the whole plan runs inside a single transaction: every action commits
    /// together, or none of them do - the transaction is aborted and the
    /// document is exactly as the architect left it.
    /// </summary>
    internal static class ApplyCommand
    {
        /// <summary>
        /// What this session has applied, newest last, keyed by plan. It is the
        /// host's own record - the raw material of the change set, and the
        /// answer to <c>/changes</c>. Same role as the Revit host's own record.
        /// </summary>
        private static readonly Dictionary<string, List<object>> Applied =
            new Dictionary<string, List<object>>();

        public static Dictionary<string, object> Changes(Dictionary<string, object> request)
        {
            string planId = Json.String(request, "transaction", Json.String(request, "plan_id", ""));
            var changes = new List<object>();
            if (planId.Length > 0)
            {
                if (Applied.TryGetValue(planId, out var found)) changes.AddRange(found);
            }
            else
            {
                foreach (var entry in Applied) changes.AddRange(entry.Value);
            }
            return new Dictionary<string, object> { { "changes", changes } };
        }

        public static Dictionary<string, object> Run(Document doc, Dictionary<string, object> request)
        {
            if (doc.IsReadOnly)
                throw new HostException(Protocol.ErrReadOnly, "the document is read-only");

            string planId = Json.String(request, "plan_id", "plan");
            var actions = Json.List(request, "actions");
            var changes = new List<object>();

            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                try
                {
                    for (int index = 0; index < actions.Count; index++)
                    {
                        var action = actions[index] as Dictionary<string, object>;
                        if (action == null)
                            throw HostException.Unsupported("action " + index + " is not an object");
                        changes.Add(Perform(tr, doc.Database, action));
                    }
                }
                catch (Exception)
                {
                    tr.Abort();
                    throw;
                }
                tr.Commit();
            }

            if (!Applied.ContainsKey(planId)) Applied[planId] = new List<object>();
            Applied[planId].AddRange(changes);

            return new Dictionary<string, object>
                { { "plan_id", planId }, { "changes", changes }, { "committed", true } };
        }

        private static Dictionary<string, object> Perform(
            Transaction tr, Database db, Dictionary<string, object> action)
        {
            string name = Json.String(action, "action", "");
            string handleHex = Json.String(action, "id", "");
            Entity entity = string.IsNullOrEmpty(handleHex) || name == Protocol.UpdateSchedule
                ? null : QueryCommands.Resolve(tr, db, handleHex);

            if (entity == null && name != Protocol.Create && name != Protocol.UpdateSchedule)
                throw HostException.NotFound(handleHex);

            switch (name)
            {
                case Protocol.Move: return Move(db, entity, action);
                case Protocol.Resize: return Resize(db, entity, action);
                case Protocol.Rotate: return Rotate(db, entity, action);
                case Protocol.Delete: return Delete(entity);
                case Protocol.SetText: return SetText(tr, db, entity, action);
                case Protocol.SetParameter: return SetParameter(tr, db, entity, action);
                case Protocol.UpdateDimension: return UpdateDimension(entity);
                case Protocol.UpdateSchedule: return UpdateSchedule(tr, db, action);
                case Protocol.Create:
                    throw HostException.Unsupported(
                        "creating entities is not implemented: a new parking bay or road is a " +
                        "design decision that belongs to the architect, not to a correction");
                default:
                    throw HostException.Unsupported("unsupported action: " + name);
            }
        }

        // ------------------------------------------------------------------
        private static Dictionary<string, object> Move(
            Database db, Entity entity, Dictionary<string, object> action)
        {
            double metres = Json.Number(action, "distance", 0.0);
            string direction = Json.String(action, "direction", "north");
            Vector3d vector = DirectionVector(db, direction, metres);

            var before = EntityView.BoxOf(db, entity.Bounds);
            entity.UpgradeOpen();
            entity.TransformBy(Matrix3d.Displacement(vector));
            var after = EntityView.BoxOf(db, entity.Bounds);
            return Change(entity, "position", before, after);
        }

        private static Vector3d DirectionVector(Database db, string direction, double metres)
        {
            double units = Units.ToDrawingUnits(db, metres);
            switch (direction)
            {
                case "north": return new Vector3d(0, units, 0);
                case "south": return new Vector3d(0, -units, 0);
                case "east": return new Vector3d(units, 0, 0);
                case "west": return new Vector3d(-units, 0, 0);
                default: throw HostException.Unsupported("unknown direction: " + direction);
            }
        }

        /// <summary>
        /// Resize a rectangular polyline (a parking bay, a room outline) by
        /// rebuilding its four corners around one axis; a block reference with
        /// no dynamic width parameter is scaled instead. Anything else has no
        /// editable "width" here, same honest refusal as the Revit host.
        /// </summary>
        private static Dictionary<string, object> Resize(
            Database db, Entity entity, Dictionary<string, object> action)
        {
            string parameter = Json.String(action, "parameter", "width");
            double metres = Json.Number(action, "value", 0.0);
            string anchor = Json.String(action, "anchor", "south_west");

            if (entity is Polyline polyline && polyline.NumberOfVertices == 4 && entity.Bounds.HasValue)
            {
                var box = entity.Bounds.Value;
                string axis = EntityView.WidthAxisOf(db, entity);
                bool alongX = (parameter == "width") == (axis == "x");
                double before = Units.Tidy(Units.ToMetres(db,
                    alongX ? box.MaxPoint.X - box.MinPoint.X : box.MaxPoint.Y - box.MinPoint.Y));
                double target = Units.ToDrawingUnits(db, metres);

                double minX = box.MinPoint.X, maxX = box.MaxPoint.X;
                double minY = box.MinPoint.Y, maxY = box.MaxPoint.Y;
                if (alongX)
                {
                    if (anchor.Contains("east")) minX = maxX - target; else maxX = minX + target;
                }
                else
                {
                    if (anchor.Contains("north")) minY = maxY - target; else maxY = minY + target;
                }

                polyline.UpgradeOpen();
                polyline.SetPointAt(0, new Point2d(minX, minY));
                polyline.SetPointAt(1, new Point2d(maxX, minY));
                polyline.SetPointAt(2, new Point2d(maxX, maxY));
                polyline.SetPointAt(3, new Point2d(minX, maxY));
                return Change(entity, parameter, before, Units.Tidy(metres));
            }

            if (entity is BlockReference block)
            {
                var box = entity.Bounds;
                if (box == null) throw HostException.Unsupported("the block has no geometry to scale from");
                string axis = EntityView.WidthAxisOf(db, entity);
                bool alongX = (parameter == "width") == (axis == "x");
                double current = Units.ToMetres(db, alongX
                    ? box.Value.MaxPoint.X - box.Value.MinPoint.X
                    : box.Value.MaxPoint.Y - box.Value.MinPoint.Y);
                if (current <= 0) throw HostException.Unsupported("cannot scale from zero extent");
                double factor = metres / current;

                block.UpgradeOpen();
                block.ScaleFactors = alongX
                    ? new Scale3d(block.ScaleFactors.X * factor, block.ScaleFactors.Y, block.ScaleFactors.Z)
                    : new Scale3d(block.ScaleFactors.X, block.ScaleFactors.Y * factor, block.ScaleFactors.Z);
                return Change(entity, parameter, Units.Tidy(current), Units.Tidy(metres));
            }

            throw HostException.Unsupported(
                "cannot resize " + EntityView.CategoryOf(entity) + " by '" + parameter +
                "': it is neither a rectangular polyline nor a block reference. Let the " +
                "architect do it.");
        }

        private static Dictionary<string, object> Rotate(
            Database db, Entity entity, Dictionary<string, object> action)
        {
            double degrees = Json.Number(action, "angle", 0.0);
            var box = entity.Bounds;
            if (box == null) throw HostException.Unsupported("the entity has no geometry");

            Point3d centre = new Point3d(
                (box.Value.MinPoint.X + box.Value.MaxPoint.X) / 2.0,
                (box.Value.MinPoint.Y + box.Value.MaxPoint.Y) / 2.0,
                (box.Value.MinPoint.Z + box.Value.MaxPoint.Z) / 2.0);
            double before = EntityView.RotationOf(entity);
            entity.UpgradeOpen();
            entity.TransformBy(Matrix3d.Rotation(degrees * Math.PI / 180.0, Vector3d.ZAxis, centre));
            return Change(entity, "rotation", before, EntityView.RotationOf(entity));
        }

        private static Dictionary<string, object> Delete(Entity entity)
        {
            var change = Change(entity, "existence", "present", "removed");
            change["kind"] = "removed";
            entity.UpgradeOpen();
            entity.Erase();
            return change;
        }

        private static Dictionary<string, object> SetText(
            Transaction tr, Database db, Entity entity, Dictionary<string, object> action)
        {
            string text = Json.String(action, "text", "");
            entity.UpgradeOpen();
            if (entity is DBText dbText)
            {
                string before = dbText.TextString;
                dbText.TextString = text;
                return Change(entity, "text", before, text);
            }
            if (entity is MText mtext)
            {
                string before = mtext.Text;
                mtext.Contents = text;
                return Change(entity, "text", before, text);
            }
            var tagged = EntityView.ReadTag(entity) ?? new Dictionary<string, object>();
            string previous = Json.String(tagged, "label", "");
            tagged["label"] = text;
            EntityView.WriteTag(tr, db, entity, tagged);
            return Change(entity, "text", previous, text);
        }

        /// <summary>
        /// There is no "parameter" object on a plain AutoCAD entity, so this
        /// writes into the Archagent tag's properties bag - the same bag
        /// <c>/element</c> and <c>/find</c> read back.
        /// </summary>
        private static Dictionary<string, object> SetParameter(
            Transaction tr, Database db, Entity entity, Dictionary<string, object> action)
        {
            string name = Json.String(action, "parameter", "");
            if (string.IsNullOrEmpty(name)) throw HostException.Unsupported("no parameter name given");
            object value = action.ContainsKey("value") ? action["value"] : null;

            var tagged = EntityView.ReadTag(entity) ?? new Dictionary<string, object>();
            var properties = tagged.TryGetValue("properties", out var existing)
                ? existing as Dictionary<string, object> ?? new Dictionary<string, object>()
                : new Dictionary<string, object>();
            object before = properties.TryGetValue(name, out var previous) ? previous : null;
            properties[name] = value;
            tagged["properties"] = properties;
            EntityView.WriteTag(tr, db, entity, tagged);
            return Change(entity, name, before, value);
        }

        /// <summary>
        /// An AutoCAD dimension reports the geometry it measures; it is not
        /// set. Recomputing is therefore a read - same as the Revit host.
        /// </summary>
        private static Dictionary<string, object> UpdateDimension(Entity entity)
        {
            if (!(entity is Dimension dimension))
                throw HostException.Unsupported("not a dimension");
            double after = Units.Tidy(dimension.Measurement);
            dimension.UpgradeOpen();
            dimension.RecomputeDimensionBlock(true);
            var change = Change(entity, "value", after, after);
            change["kind"] = "annotation";
            return change;
        }

        /// <summary>
        /// A <see cref="Table"/> entity is the nearest thing to a Revit
        /// schedule; there is nothing to write, only to recompute and re-read.
        /// </summary>
        private static Dictionary<string, object> UpdateSchedule(
            Transaction tr, Database db, Dictionary<string, object> action)
        {
            string handleHex = Json.String(action, "id", "");
            var table = QueryCommands.Resolve(tr, db, handleHex) as Table;
            if (table == null) throw HostException.NotFound(handleHex);

            table.UpgradeOpen();
            table.GenerateLayout();
            int rows = table.Rows.Count;
            return new Dictionary<string, object>
            {
                { "element_id", table.Handle.ToString() },
                { "property", "rows" },
                { "before", rows },
                { "after", rows },
                { "sheet", string.Empty },
                { "kind", "schedule" },
            };
        }

        private static Dictionary<string, object> Change(
            Entity entity, string property, object before, object after)
        {
            return new Dictionary<string, object>
            {
                { "element_id", entity.Handle.ToString() },
                { "property", property },
                { "before", before },
                { "after", after },
                { "sheet", string.Empty },
                { "kind", "modified" },
            };
        }
    }
}
