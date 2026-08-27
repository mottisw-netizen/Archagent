using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace Archagent.Revit.Commands
{
    /// <summary>
    /// Applies a whole correction plan in one transaction group.
    ///
    /// This is the only place in the add-in that writes. It is a batch because
    /// Revit only permits a transaction inside a single API context: a plan
    /// that arrived one action per HTTP request could not be atomic. Here it
    /// is - every action commits, or the group is rolled back and the document
    /// is exactly as the architect left it.
    /// </summary>
    internal static class ApplyCommand
    {
        /// <summary>
        /// What this session has applied, newest last, keyed by plan.
        /// It is the host's own record - the raw material of the change set, and
        /// the answer to <c>/changes</c>. It lives only as long as the session,
        /// because the durable record is the change set Archagent writes.
        /// </summary>
        private static readonly Dictionary<string, List<object>> Applied =
            new Dictionary<string, List<object>>();

        public static Dictionary<string, object> Changes(Dictionary<string, object> request)
        {
            string planId = Json.String(request, "transaction",
                Json.String(request, "plan_id", ""));
            var changes = new List<object>();
            if (planId.Length > 0)
            {
                List<object> found;
                if (Applied.TryGetValue(planId, out found)) changes.AddRange(found);
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

            using (var group = new TransactionGroup(doc, "Archagent " + planId))
            {
                group.Start();
                try
                {
                    for (int index = 0; index < actions.Count; index++)
                    {
                        var action = actions[index] as Dictionary<string, object>;
                        if (action == null)
                            throw HostException.Unsupported("action " + index + " is not an object");
                        changes.Add(Perform(doc, action, index));
                    }
                }
                catch (Exception)
                {
                    group.RollBack();
                    throw;
                }

                // Assimilate keeps the plan as a single undo step for the architect.
                group.Assimilate();
            }

            // Recorded only after the group is assimilated: a rolled-back plan
            // did not happen, and must not appear in /changes.
            if (!Applied.ContainsKey(planId)) Applied[planId] = new List<object>();
            Applied[planId].AddRange(changes);

            return new Dictionary<string, object>
            {
                { "plan_id", planId },
                { "changes", changes },
                { "committed", true },
            };
        }

        private static Dictionary<string, object> Perform(
            Document doc, Dictionary<string, object> action, int index)
        {
            string name = Json.String(action, "action", "");
            string uniqueId = Json.String(action, "id", "");
            Element element = string.IsNullOrEmpty(uniqueId) ? null : doc.GetElement(uniqueId);

            if (element == null && name != Protocol.Create && name != Protocol.UpdateSchedule)
                throw HostException.NotFound(uniqueId);

            using (var transaction = new Transaction(doc, "Archagent " + name + " " + index))
            {
                transaction.Start();
                Dictionary<string, object> change;
                switch (name)
                {
                    case Protocol.Move: change = Move(doc, element, action); break;
                    case Protocol.Resize: change = Resize(doc, element, action); break;
                    case Protocol.Rotate: change = Rotate(doc, element, action); break;
                    case Protocol.Delete: change = Delete(doc, element); break;
                    case Protocol.SetText: change = SetText(element, action); break;
                    case Protocol.SetParameter: change = SetParameter(element, action); break;
                    case Protocol.UpdateDimension: change = UpdateDimension(doc, element, action); break;
                    case Protocol.UpdateSchedule: change = UpdateSchedule(doc, action); break;
                    case Protocol.Create:
                        throw HostException.Unsupported(
                            "creating elements is not implemented: a new parking bay or wall " +
                            "is a design decision that belongs to the architect, not to a " +
                            "correction");
                    default:
                        throw HostException.Unsupported("unsupported action: " + name);
                }
                transaction.Commit();
                return change;
            }
        }

        // ------------------------------------------------------------------
        private static Dictionary<string, object> Move(
            Document doc, Element element, Dictionary<string, object> action)
        {
            double metres = Json.Number(action, "distance", 0.0);
            string direction = Json.String(action, "direction", "north");
            XYZ vector = DirectionVector(direction, metres);

            var before = ElementView.BoxOf(element.get_BoundingBox(null));
            ElementTransformUtils.MoveElement(doc, element.Id, vector);
            var after = ElementView.BoxOf(element.get_BoundingBox(null));

            return Change(element, "position", before, after);
        }

        private static XYZ DirectionVector(string direction, double metres)
        {
            double feet = Units.ToFeet(metres);
            switch (direction)
            {
                case "north": return new XYZ(0, feet, 0);
                case "south": return new XYZ(0, -feet, 0);
                case "east": return new XYZ(feet, 0, 0);
                case "west": return new XYZ(-feet, 0, 0);
                default: throw HostException.Unsupported("unknown direction: " + direction);
            }
        }

        /// <summary>
        /// Resize by the element's own parameter where it has one - a parking
        /// family's Width, a wall's length - because changing geometry by
        /// stretching a bounding box would break constraints Revit maintains.
        /// </summary>
        private static Dictionary<string, object> Resize(
            Document doc, Element element, Dictionary<string, object> action)
        {
            string parameter = Json.String(action, "parameter", "width");
            double metres = Json.Number(action, "value", 0.0);

            Parameter target = FindDimensionParameter(element, parameter);
            if (target != null && !target.IsReadOnly)
            {
                double before = Units.Tidy(Units.ToMetres(target.AsDouble()));
                target.Set(Units.ToFeet(metres));
                double after = Units.Tidy(Units.ToMetres(target.AsDouble()));
                return Change(element, parameter, before, after);
            }

            if (element is Wall wall && parameter == "length" &&
                wall.Location is LocationCurve curve)
            {
                var line = curve.Curve as Line;
                if (line != null)
                {
                    double before = Units.Tidy(Units.ToMetres(line.Length));
                    string anchor = Json.String(action, "anchor", "south_west");
                    XYZ start = line.GetEndPoint(0);
                    XYZ end = line.GetEndPoint(1);
                    XYZ unit = (end - start).Normalize();
                    double feet = Units.ToFeet(metres);
                    XYZ newStart = anchor.Contains("north") || anchor.Contains("east")
                        ? end - unit * feet
                        : start;
                    XYZ newEnd = newStart + unit * feet;
                    curve.Curve = Line.CreateBound(newStart, newEnd);
                    return Change(element, parameter, before, Units.Tidy(metres));
                }
            }

            throw HostException.Unsupported(
                "cannot resize " + ElementView.CategoryOf(element) + " by '" + parameter +
                "': the element has no such editable parameter. Change the family type, or " +
                "let the architect do it.");
        }

        private static Parameter FindDimensionParameter(Element element, string parameter)
        {
            // Instance first, then type: a family may drive width from either.
            string[] names = parameter == "width"
                ? new[] { "Width", "רוחב", "b" }
                : parameter == "length"
                    ? new[] { "Length", "Depth", "אורך", "עומק" }
                    : new[] { "Height", "גובה" };

            foreach (string name in names)
            {
                var found = element.LookupParameter(name);
                if (found != null && found.StorageType == StorageType.Double && !found.IsReadOnly)
                    return found;
            }
            return null;
        }

        private static Dictionary<string, object> Rotate(
            Document doc, Element element, Dictionary<string, object> action)
        {
            double degrees = Json.Number(action, "angle", 0.0);
            var bbox = element.get_BoundingBox(null);
            if (bbox == null) throw HostException.Unsupported("the element has no geometry");

            XYZ centre = (bbox.Min + bbox.Max) * 0.5;
            Line axis = Line.CreateBound(centre, centre + XYZ.BasisZ);
            double before = ElementView.RotationOf(element);
            ElementTransformUtils.RotateElement(doc, element.Id, axis, degrees * Math.PI / 180.0);
            return Change(element, "rotation", before, ElementView.RotationOf(element));
        }

        private static Dictionary<string, object> Delete(Document doc, Element element)
        {
            var change = Change(element, "existence", "present", "removed");
            change["kind"] = "removed";
            doc.Delete(element.Id);
            return change;
        }

        private static Dictionary<string, object> SetText(
            Element element, Dictionary<string, object> action)
        {
            string text = Json.String(action, "text", "");
            if (element is TextNote note)
            {
                string before = note.Text;
                note.Text = text;
                return Change(element, "text", before, text);
            }
            var parameter = element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK);
            if (parameter != null && !parameter.IsReadOnly)
            {
                string before = parameter.AsString();
                parameter.Set(text);
                return Change(element, "text", before, text);
            }
            throw HostException.Unsupported("this element has no editable text");
        }

        private static Dictionary<string, object> SetParameter(
            Element element, Dictionary<string, object> action)
        {
            string name = Json.String(action, "parameter", "");
            var parameter = element.LookupParameter(name);
            if (parameter == null) throw HostException.Unsupported("no parameter named " + name);
            if (parameter.IsReadOnly) throw HostException.Unsupported(name + " is read-only");

            object value = action.ContainsKey("value") ? action["value"] : null;
            switch (parameter.StorageType)
            {
                case StorageType.Double:
                {
                    double before = Units.Tidy(Units.ToMetres(parameter.AsDouble()));
                    parameter.Set(Units.ToFeet(Convert.ToDouble(value)));
                    return Change(element, name, before,
                        Units.Tidy(Units.ToMetres(parameter.AsDouble())));
                }
                case StorageType.Integer:
                {
                    int before = parameter.AsInteger();
                    parameter.Set(Convert.ToInt32(value));
                    return Change(element, name, before, parameter.AsInteger());
                }
                default:
                {
                    string before = parameter.AsString();
                    parameter.Set(Convert.ToString(value));
                    return Change(element, name, before, parameter.AsString());
                }
            }
        }

        /// <summary>
        /// A Revit dimension reports the geometry it measures; it is not set.
        /// Recomputing is therefore a read, and the "change" is the value the
        /// architect will now see on the sheet.
        /// </summary>
        private static Dictionary<string, object> UpdateDimension(
            Document doc, Element element, Dictionary<string, object> action)
        {
            if (!(element is Dimension dimension))
                throw HostException.Unsupported("not a dimension");

            double? value = dimension.Value;
            double after = value.HasValue ? Units.Tidy(Units.ToMetres(value.Value)) : 0.0;
            // Touch the element so Revit regenerates the annotation.
            doc.Regenerate();
            var change = Change(element, "value", after, after);
            change["kind"] = "annotation";
            return change;
        }

        /// <summary>
        /// Revit schedules recompute themselves from the model - there is
        /// nothing to write. The change record says so, and the validator
        /// re-reads the schedule to confirm.
        /// </summary>
        private static Dictionary<string, object> UpdateSchedule(
            Document doc, Dictionary<string, object> action)
        {
            string id = Json.String(action, "id", "");
            var schedule = doc.GetElement(id) as ViewSchedule;
            if (schedule == null)
            {
                foreach (var candidate in new FilteredElementCollector(doc)
                             .OfClass(typeof(ViewSchedule)))
                {
                    if (candidate.Name == id) { schedule = (ViewSchedule)candidate; break; }
                }
            }
            if (schedule == null) throw HostException.NotFound(id);

            doc.Regenerate();
            int rows = schedule.GetTableData().GetSectionData(SectionType.Body).NumberOfRows;
            return new Dictionary<string, object>
            {
                { "element_id", schedule.UniqueId },
                { "property", "rows" },
                { "before", rows },
                { "after", rows },
                { "sheet", string.Empty },
                { "kind", "schedule" },
            };
        }

        private static Dictionary<string, object> Change(
            Element element, string property, object before, object after)
        {
            return new Dictionary<string, object>
            {
                { "element_id", element.UniqueId },
                { "property", property },
                { "before", before },
                { "after", after },
                { "sheet", string.Empty },
                { "kind", "modified" },
            };
        }
    }
}
