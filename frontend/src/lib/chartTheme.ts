import { useMemo } from "react";
import { useTheme } from "../state/ThemeContext";

/**
 * Recharts takes concrete colors for SVG presentation attributes; custom
 * properties are resolved to their computed value through a hidden probe
 * element so charts follow the active theme's tokens.
 */
let probe: HTMLSpanElement | null = null;

function resolveVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  if (!probe) {
    probe = document.createElement("span");
    probe.style.display = "none";
    document.body.appendChild(probe);
  }
  probe.style.color = "";
  probe.style.color = `var(${name})`;
  const value = getComputedStyle(probe).color;
  return value || fallback;
}

export interface ChartTheme {
  grid: string;
  axis: string;
  axisText: string;
  tooltipBackground: string;
  tooltipBorder: string;
  series: string[];
}

export function readChartTheme(_theme?: string): ChartTheme {
  return {
    grid: resolveVar("--chart-cartesian-grid-stroke-color", "rgba(141,141,141,0.16)"),
    axis: resolveVar("--chart-axis-stroke-color", "#4b4b4b"),
    axisText: resolveVar("--chart-axis-text-color", "rgba(255,255,255,0.5)"),
    tooltipBackground: resolveVar("--global-color-gray-50", "#000"),
    tooltipBorder: resolveVar("--global-border-color-default", "#303030"),
    series: Array.from({ length: 8 }, (_, i) =>
      resolveVar(`--chart-color-${i + 1}`, "#4096f3")
    ),
  };
}

export function useChartTheme(): ChartTheme {
  const { theme } = useTheme();
  // Re-resolve the token values whenever the theme class flips.
  return useMemo(() => readChartTheme(theme), [theme]);
}
