using Autodesk.Revit.DB;

namespace Archagent.Revit
{
    /// <summary>
    /// Revit works in decimal feet internally. The protocol is metres and square
    /// metres, always - so the conversion lives here, at the boundary, and
    /// nothing above it ever sees a foot.
    /// </summary>
    internal static class Units
    {
        public const double FeetPerMetre = 3.280839895013123;

        public static double ToMetres(double feet) => feet / FeetPerMetre;

        public static double ToFeet(double metres) => metres * FeetPerMetre;

        public static double AreaToSquareMetres(double squareFeet) =>
            squareFeet / (FeetPerMetre * FeetPerMetre);

        public static double AreaToSquareFeet(double squareMetres) =>
            squareMetres * (FeetPerMetre * FeetPerMetre);

        /// <summary>Round a metre value the way a report would print it.</summary>
        public static double Tidy(double metres) => System.Math.Round(metres, 6);

        public static XYZ MetresToXYZ(double x, double y, double z = 0.0) =>
            new XYZ(ToFeet(x), ToFeet(y), ToFeet(z));
    }
}
