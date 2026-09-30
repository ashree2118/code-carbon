function withUnit(value: number, units: [number, string][]): string {
  for (const [scale, unit] of units) {
    if (Math.abs(value) >= scale) {
      return `${(value / scale).toPrecision(3)} ${unit}`;
    }
  }
  const [scale, unit] = units[units.length - 1];
  return `${(value / scale).toPrecision(3)} ${unit}`;
}

/** Energy in kWh, shown in the most readable unit. */
export function formatEnergy(kwh: number | null): string {
  if (kwh === null) return "Unavailable";
  return withUnit(kwh, [
    [1, "kWh"],
    [1e-3, "Wh"],
    [1e-6, "mWh"],
    [1e-9, "µWh"],
  ]);
}

/** CO₂ in kg, shown in the most readable unit. */
export function formatCo2(kg: number | null): string {
  if (kg === null) return "Unavailable";
  return withUnit(kg, [
    [1, "kg"],
    [1e-3, "g"],
    [1e-6, "mg"],
    [1e-9, "µg"],
  ]);
}

export function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "Unavailable";
  return seconds < 1
    ? `${(seconds * 1000).toFixed(1)} ms`
    : `${seconds.toFixed(2)} s`;
}
