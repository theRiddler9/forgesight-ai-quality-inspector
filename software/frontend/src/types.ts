export type Decision = 'PASS' | 'FAIL' | 'RECHECK';

export interface InspectionEvent {
  event_id: string;
  timestamp: string;
  scenario: string;
  result: Decision;
  part_id: string;
  decision_reasons: string[];
  faults: string[];
  defects: Array<{ type: string; confidence: number; bbox_normalized: number[] | null }>;
  poka_yoke: {
    part_present: boolean;
    position_ok: boolean | null;
    orientation_ok: boolean | null;
    hole_present: boolean | null;
    size_in_range: boolean | null;
    reasons: string[];
  };
  latency_ms: Record<'capture' | 'preprocess' | 'poka_yoke' | 'inference' | 'postprocess' | 'decision' | 'io' | 'total', number>;
  image: { input_uri: string; evidence_uri: string | null; sha256: string | null; source_id: string };
  model: { name: string; version: string; runtime: string; artifact_sha256: string | null; purpose?: 'adapter_test_fixture' | 'trained_unverified' | 'trained_validated' };
  configuration_version: string;
  simulation: { synthetic_fixture: boolean; scenario_driven_detector: boolean; mock_io: boolean; test_model?: boolean };
  mock_io_state?: { green: boolean; red: boolean; amber: boolean; buzzer: boolean; ring_light_pwm: number };
}

export interface HistoryResponse {
  items: InspectionEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface Metrics {
  total: number;
  PASS: number;
  FAIL: number;
  RECHECK: number;
  average_latency_ms: number | null;
}

export interface Health {
  status: string;
  detector: string;
  frame_source: string;
  io: string;
  mock_io_state: { green: boolean; red: boolean; amber: boolean; buzzer: boolean; ring_light_pwm: number };
}

export interface Review {
  review_id: string;
  event_id: string;
  reviewed_at: string;
  reviewer_id: string;
  corrected_result: Decision;
  note: string;
}
