// Pure helpers for the SCOS Agent Control Center prototype.
// No runtime clocks, no randomness — everything here is deterministic.

import { AGENTS, TASKS } from "./mock-data";
import type {
  Agent,
  AgentId,
  MascotMood,
  Task,
  TaskStatus,
} from "./types";

/** Tiny classnames joiner (no external dependency). */
export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

export function getTaskById(id: string | null): Task | undefined {
  if (!id) return undefined;
  return TASKS.find((task) => task.id === id);
}

export function getAgentById(id: AgentId): Agent | undefined {
  return AGENTS.find((agent) => agent.id === id);
}

/** Maps a task status to the mascot's visual mood. */
export function taskStatusToMood(status: TaskStatus | undefined): MascotMood {
  switch (status) {
    case "in-progress":
      return "working";
    case "blocked":
      return "blocked";
    case "approved":
    case "done":
      return "approved";
    case "in-review":
      return "review";
    default:
      return "idle";
  }
}

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  backlog: "Backlog",
  "in-progress": "In Progress",
  blocked: "Blocked",
  "in-review": "In Review",
  approved: "Approved",
  done: "Done",
};

/** Column order for the kanban board. */
export const BOARD_COLUMNS: TaskStatus[] = [
  "backlog",
  "in-progress",
  "in-review",
  "blocked",
  "approved",
  "done",
];

export interface MascotView {
  mood: MascotMood;
  message: string;
  nextAction: string;
  taskSummary: string;
}

/** Derives everything the mascot panel needs from the selected task. */
export function deriveMascotView(task: Task | undefined): MascotView {
  if (!task) {
    return {
      mood: "idle",
      message: "All quiet. Select a task and I'll help you read the room.",
      nextAction: "Pick a task from the board to get a recommendation.",
      taskSummary: "No task selected.",
    };
  }

  const agent = getAgentById(task.assignee);
  const who = agent ? agent.name : task.assignee;
  const taskSummary = `${task.code} · ${task.title} (${who})`;

  switch (task.status) {
    case "blocked":
      return {
        mood: "blocked",
        message: `${task.code} is blocked. ${task.blockedReason ?? "It needs a dependency before it can move."}`,
        nextAction:
          "Use Result Inbox to track the blocker, keep Merge Queue on Hold, then ask Codex after preflight is clean.",
        taskSummary,
      };
    case "in-review":
      return {
        mood: "review",
        message: `${who} is verifying ${task.code}. Do not approve the merge until review evidence is complete.`,
        nextAction:
          "Use Result Inbox for the review result, then follow Decision Guidance in Merge Queue.",
        taskSummary,
      };
    case "approved":
    case "done":
      return {
        mood: "approved",
        message: `${task.code} passed. Nice — this one is ready to move on.`,
        nextAction:
          task.status === "approved"
            ? "Check Decision Guidance and approve only if required evidence is present."
            : "Nothing to do — it's already shipped.",
        taskSummary,
      };
    case "in-progress":
      return {
        mood: "working",
        message: `${who} is actively building ${task.code}.`,
        nextAction:
          "Copy the prepared prompt manually, then paste the builder result into Result Inbox.",
        taskSummary,
      };
    default:
      return {
        mood: "idle",
        message: `${task.code} is queued in the backlog.`,
        nextAction:
          "Use Prompt Builder to prepare the next manual handoff before requesting review.",
        taskSummary,
      };
  }
}

/** Formats a hardcoded ISO string as a compact, locale-independent label. */
export function formatTimestamp(iso: string): string {
  // Deterministic manual formatting — avoids locale/timezone drift and any clock use.
  const [datePart, timePartRaw] = iso.split("T");
  if (!datePart || !timePartRaw) return iso;
  const [year, month, day] = datePart.split("-");
  const time = timePartRaw.replace("Z", "").slice(0, 5); // HH:MM
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const monthLabel = months[Number(month) - 1] ?? month;
  return `${monthLabel} ${Number(day)}, ${year} · ${time} UTC`;
}
