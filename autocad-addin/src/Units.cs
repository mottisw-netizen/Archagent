using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;

namespace Archagent.Acad
{
    /// <summary>
    /// AutoCAD drawings carry their own linear unit (INSUNITS), unlike Revit's
    /// fixed decimal feet - a metric consultant's drawing is usually metres or
    /// millimetres, an imperial one feet or inches. The protocol is always
    /// metres and square metres, so the conversion factor is read from the
    /// database once, at the boundary, and nothing above it ever sees a
    /// drawing unit.
    /// </summary>
    internal static class Units
    {
        //: INSUNITS value -> metres per one drawing unit.
        private static readonly Dictionary<int, double> MetresPerUnit = new Dictionary<int, double>
        {
            { (int)UnitsValue.Millimeters, 0.001 },
            { (int)UnitsValue.Centimeters, 0.01 },
            { (int)UnitsValue.Meters, 1.0 },
            { (int)UnitsValue.Kilometers, 1000.0 },
            { (int)UnitsValue.Inches, 0.0254 },
            { (int)UnitsValue.Feet, 0.3048 },
            { (int)UnitsValue.Yards, 0.9144 },
            { (int)UnitsValue.Miles, 1609.344 },
        };

        /// <summary>
        /// Metres per drawing unit for this database. Falls back to 1:1
        /// (assume metres) for INSUNITS = Undefined - a drawing with no unit
        /// set is far more likely to be metric than not, and saying so plainly
        /// beats guessing feet.
        /// </summary>
        public static double MetresPer(Database db)
        {
            int insunits = (int)db.Insunits;
            return MetresPerUnit.TryGetValue(insunits, out double factor) ? factor : 1.0;
        }

        public static double ToMetres(Database db, double drawingUnits) =>
            drawingUnits * MetresPer(db);

        public static double ToDrawingUnits(Database db, double metres) =>
            metres / MetresPer(db);

        public static double AreaToSquareMetres(Database db, double squareDrawingUnits)
        {
            double factor = MetresPer(db);
            return squareDrawingUnits * factor * factor;
        }

        /// <summary>Round a metre value the way a report would print it.</summary>
        public static double Tidy(double metres) => Math.Round(metres, 6);
    }
}
