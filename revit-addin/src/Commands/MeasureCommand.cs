using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;

namespace Archagent.Revit.Commands
{
    /// <summary>
    /// Measurement, from Revit's own geometry.
    ///
    /// The rule the whole product rests on is that a number in a report came
    /// from a measurement tool. Here that means: read it from the model. What
    /// this host cannot measure it says so about - it returns
    /// <c>unsupported</c>, and the agent computes that metric from the geometry
    /// it was given rather than inventing one.
    /// </summary>
    internal static class MeasureCommand
    {
        public static Dictionary<string, object> Run(Document doc, Dictionary<string, object> request)
        {
            var subject = Json.Dict(request, "subject");
            string metric = Json.String(request, "metric", "");
            string basis = Json.String(request, "basis", "clear");

            switch (metric)
            {
                case "width":
                case "length":
                case "height":
                    return Dimension(doc, subject, metric, basis);
                case "area":
                    return Area(doc, subject, basis);
                case "count":
                    return Count(doc, subject);
                case "setback":
                    return Setback(doc, subject, basis);
                case "floor_area":
                    return FloorArea(doc, subject, basis);
                default:
                    // clear_width and clear_distance are relationships between
                    // elements: the agent computes those from the boxes we
                    // already gave it, and the answer is identical.
                    throw HostException.Unsupported("this host does not measure " + metric);
            }
        }

        private static Element Single(Document doc, Dictionary<string, object> subject)
        {
            string id = Json.String(subject, "element_id", "");
            if (!string.IsNullOrEmpty(id)) return QueryCommands.Resolve(doc, id);

            var selector = Json.Dict(subject, "selector");
            var found = QueryCommands.Find(doc,
                new Dictionary<string, object> { { "filter", selector } });
            var ids = (List<object>)found["elements"];
            if (ids.Count == 0) throw HostException.NotFound(Json.Describe(selector));
            if (ids.Count > 1)
                throw new HostException(Protocol.ErrAmbiguous,
                    "subject matches " + ids.Count + " elements", ids.ToArray());
            return QueryCommands.Resolve(doc, Convert.ToString(ids[0]));
        }

        private static Dictionary<string, object> Dimension(
            Document doc, Dictionary<string, object> subject, string metric, string basis)
        {
            var element = Single(doc, subject);
            var parameter = element.LookupParameter(
                metric == "width" ? "Width" : metric == "length" ? "Length" : "Height");
            if (parameter != null && parameter.StorageType == StorageType.Double)
                return Result(Units.Tidy(Units.ToMetres(parameter.AsDouble())), "m", basis,
                    "parameter:" + parameter.Definition.Name);

            var bbox = element.get_BoundingBox(null);
            if (bbox == null) throw new HostException(Protocol.ErrMeasurement, "no geometry");

            double x = Units.ToMetres(bbox.Max.X - bbox.Min.X);
            double y = Units.ToMetres(bbox.Max.Y - bbox.Min.Y);
            double z = Units.ToMetres(bbox.Max.Z - bbox.Min.Z);
            string axis = ElementView.WidthAxisOf(element);
            double value = metric == "height" ? z
                : metric == "width" ? (axis == "x" ? x : y)
                : (axis == "x" ? y : x);
            return Result(Units.Tidy(value), "m", basis, "bounding_box");
        }

        private static Dictionary<string, object> Area(
            Document doc, Dictionary<string, object> subject, string basis)
        {
            var element = Single(doc, subject);
            var parameter = element.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
                            ?? element.LookupParameter("Area");
            if (parameter != null && parameter.StorageType == StorageType.Double)
                return Result(Units.Tidy(Units.AreaToSquareMetres(parameter.AsDouble())),
                    "m2", basis, "parameter:Area");

            var bbox = element.get_BoundingBox(null);
            if (bbox == null) throw new HostException(Protocol.ErrMeasurement, "no geometry");
            double area = Units.ToMetres(bbox.Max.X - bbox.Min.X) *
                          Units.ToMetres(bbox.Max.Y - bbox.Min.Y);
            return Result(Units.Tidy(area), "m2", basis, "bounding_box");
        }

        private static Dictionary<string, object> Count(
            Document doc, Dictionary<string, object> subject)
        {
            var selector = Json.Dict(subject, "selector");
            var found = QueryCommands.Find(doc,
                new Dictionary<string, object> { { "filter", selector } });
            var ids = (List<object>)found["elements"];
            return Result(ids.Count, "count", "clear", "find_element");
        }

        /// <summary>
        /// Distance from an element's face to the property line on that side.
        /// Without a property line in the model there is nothing to measure
        /// against, and saying so is the only honest answer.
        /// </summary>
        private static Dictionary<string, object> Setback(
            Document doc, Dictionary<string, object> subject, string basis)
        {
            string edge = Json.String(subject, "edge", "");
            if (string.IsNullOrEmpty(edge))
                throw new HostException(Protocol.ErrMeasurement, "a setback needs an edge");

            var element = Single(doc, subject);
            var bbox = element.get_BoundingBox(null);
            if (bbox == null) throw new HostException(Protocol.ErrMeasurement, "no geometry");

            var line = new FilteredElementCollector(doc)
                .OfCategory(BuiltInCategory.OST_SiteProperty)
                .WhereElementIsNotElementType()
                .FirstOrDefault();
            if (line == null)
                throw HostException.Unsupported(
                    "the model has no property line, so a setback cannot be measured here");

            var plot = line.get_BoundingBox(null);
            if (plot == null) throw new HostException(Protocol.ErrMeasurement, "no property line geometry");

            double value;
            switch (edge)
            {
                case "north": value = Units.ToMetres(plot.Max.Y - bbox.Max.Y); break;
                case "south": value = Units.ToMetres(bbox.Min.Y - plot.Min.Y); break;
                case "east": value = Units.ToMetres(plot.Max.X - bbox.Max.X); break;
                case "west": value = Units.ToMetres(bbox.Min.X - plot.Min.X); break;
                default: throw HostException.Unsupported("unknown edge: " + edge);
            }
            return Result(Units.Tidy(value), "m", "to plot line", "property_line");
        }

        private static Dictionary<string, object> FloorArea(
            Document doc, Dictionary<string, object> subject, string basis)
        {
            double total = 0.0;
            foreach (Element area in new FilteredElementCollector(doc)
                         .OfCategory(BuiltInCategory.OST_Areas)
                         .WhereElementIsNotElementType())
            {
                var parameter = area.get_Parameter(BuiltInParameter.ROOM_AREA);
                if (parameter != null) total += Units.AreaToSquareMetres(parameter.AsDouble());
            }
            if (total <= 0.0)
                throw HostException.Unsupported(
                    "the model has no area scheme, so built floor area cannot be measured here");
            return Result(Units.Tidy(total), "m2", basis, "area_scheme");
        }

        private static Dictionary<string, object> Result(
            double value, string unit, string basis, string tool)
        {
            return new Dictionary<string, object>
            {
                { "value", value }, { "unit", unit }, { "basis", basis },
                { "tool", "revit:" + tool },
                { "details", new Dictionary<string, object>() },
            };
        }
    }
}
