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

  /** Radar center latitude from the active scenario. */
  centerLatitude: number;

  /** Radar center longitude from the active scenario. */
  centerLongitude: number;

  /** Elapsed seconds since scenario start. */
  elapsedSeconds: number;

  /** Whether the component is currently fetching data. */
  isLoading: boolean;

  /** Error message if the last fetch failed. */
  error: string | null;

  /** Callsign of the currently selected aircraft, or null if none. */
  selectedCallsign: string | null;

  /** Agent name of the most recent reply + a monotonically increasing tick.
   *  CollaborationFlow watches this to flash the corresponding agent node
   *  whenever a new reply lands in AGENT COMMS. */
  lastReplyAgent: string | null;
  lastReplyTick: number;

  /** Handle of the currently selected agent (for detail page). */
  selectedAgentHandle: string | null;

  /** Handle of the agent to filter comms panel by (null = show all). */
  chatFilterAgent: string | null;
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

  /** Select an aircraft by callsign, or deselect if null. Toggles if same callsign. */
  selectAircraft: (callsign: string | null) => void;

  /** Record that a new reply from the given agent just arrived. Bumps a
   *  tick so subscribers can detect changes even for repeated senders. */
  noteAgentReply: (agentName: string) => void;

  /** Select an agent handle for the detail page, or deselect if null. */
  setSelectedAgentHandle: (handle: string | null) => void;

  /** Set the comms panel filter to a specific agent, or null for all. */
  setChatFilterAgent: (handle: string | null) => void;
}

const initialState: AtcState = {
  aircraft: [],
  conflicts: [],
  weatherAdvisories: [],
  emergencies: [],
  lastUpdated: null,
  activeScenarioId: "SCN-A",
  centerLatitude: 40.63,
  centerLongitude: -73.68,
  elapsedSeconds: 0,
  isLoading: false,
  error: null,
  selectedCallsign: null,
  lastReplyAgent: null,
  lastReplyTick: 0,
  selectedAgentHandle: null,
  chatFilterAgent: null,
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
      activeScenarioId: snapshot.scenario_id,
      centerLatitude: snapshot.center_latitude,
      centerLongitude: snapshot.center_longitude,
      elapsedSeconds: snapshot.elapsed_seconds,
      isLoading: false,
      error: null,
    }),

  setActiveScenario: (scenarioId: string) =>
    set({ activeScenarioId: scenarioId }),

  setLoading: (loading: boolean) =>
    set({ isLoading: loading }),

  setError: (error: string | null) =>
    set({ error, isLoading: false }),

  selectAircraft: (callsign: string | null) =>
    set((state) => ({
      selectedCallsign:
        state.selectedCallsign === callsign ? null : callsign,
    })),

  noteAgentReply: (agentName: string) =>
    set({ lastReplyAgent: agentName, lastReplyTick: Date.now() }),

  setSelectedAgentHandle: (handle: string | null) =>
    set({ selectedAgentHandle: handle }),

  setChatFilterAgent: (handle: string | null) =>
    set({ chatFilterAgent: handle }),

  reset: () => set(initialState),
}));
