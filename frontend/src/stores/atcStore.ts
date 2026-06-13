/** ATC Zustand store — global state for the radar display. */

import { create } from "zustand";
import type { AircraftState, ConflictAdvisory, EmergencyDeclaration, RadarSnapshot, WeatherAdvisory } from "../lib/types";

/** All state for the ATC Guardian radar display. */
export interface AtcState {
  /** Currently tracked aircraft from the latest radar snapshot. */
  aircraft: AircraftState[];

  /** Active conflict advisories from the Conflict Detector agent. */
  conflicts: ConflictAdvisory[];

  /** Active weather advisories from the Weather Analyst agent. */
  weatherAdvisories: WeatherAdvisory[];

  /** Active emergency declarations from the Emergency Response agent. */
  emergencies: EmergencyDeclaration[];

  /** Timestamp of the most recent data update. */
  lastUpdated: string | null;

  /** ID of the currently loaded scenario. */
  activeScenarioId: string;

  /** Whether the component is currently fetching data. */
  isLoading: boolean;

  /** Error message if the last fetch failed. */
  error: string | null;
}

/** Actions for mutating ATC state. */
export interface AtcActions {
  /** Replace all state with a fresh radar snapshot from the backend. */
  setSnapshot: (snapshot: RadarSnapshot) => void;

  /** Switch the active scenario ID. */
  setActiveScenario: (scenarioId: string) => void;

  /** Set loading state. */
  setLoading: (loading: boolean) => void;

  /** Set error state. */
  setError: (error: string | null) => void;

  /** Reset the store to initial state. */
  reset: () => void;
}

const initialState: AtcState = {
  aircraft: [],
  conflicts: [],
  weatherAdvisories: [],
  emergencies: [],
  lastUpdated: null,
  activeScenarioId: "SCN-A",
  isLoading: false,
  error: null,
};

export type AtcStore = AtcState & AtcActions;

export const useAtcStore = create<AtcStore>()((set) => ({
  ...initialState,

  setSnapshot: (snapshot: RadarSnapshot) =>
    set({
      aircraft: snapshot.aircraft,
      conflicts: snapshot.conflicts,
      weatherAdvisories: snapshot.weather_advisories,
      emergencies: snapshot.emergencies,
      lastUpdated: snapshot.timestamp,
      isLoading: false,
      error: null,
    }),

  setActiveScenario: (scenarioId: string) =>
    set({ activeScenarioId: scenarioId }),

  setLoading: (loading: boolean) =>
    set({ isLoading: loading }),

  setError: (error: string | null) =>
    set({ error, isLoading: false }),

  reset: () => set(initialState),
}));
