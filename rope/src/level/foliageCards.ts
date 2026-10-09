/** Overrides in the moss mesh's local metres, independent of level pixel scaling.
 * Card numbers are stable for the pinned scene asset and generator seed. */
export interface FoliageCardEdit {
  offset?: [number, number, number];
  width?: number;
  height?: number;
  rotation?: number;
  curve?: number;
  variant?: number;
  points?: number[][];
  hidden?: boolean;
}
export type FoliageCards = Record<string, Record<string, FoliageCardEdit>>;
