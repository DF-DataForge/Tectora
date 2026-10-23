# Taakopvolging per fase (`tectora_project_tasks`)

Task follow-up per project phase, the same as the "Taken" block of the
Congristruct project dashboard (`df_congristruct_pm`), but starting from an
**empty task template**: no phases and no tasks are shipped, every company
fills them in itself.

## Configuration

*Dakmeting › Taakopvolging* (or *Project › Configuratie*):

- **Projectfases**: name, short description, order, and optionally a
  deadline for the phase milestone relative to the project's start or end date.
- **Taaksjablonen**: per phase the main tasks with their subtasks, a
  description, optional tasks (*Optie*: switched off by default, switched on
  per project) and deadlines relative to the project's start or end date.

## On the project

- A **new project** gets one milestone per phase and the tasks and subtasks
  of the templates on it (as soon as at least one phase exists). Existing
  projects start the follow-up with **Taakopvolging starten** on the dashboard.
- **Dashboard**: the block *Taken* shows the phases as a timeline, the
  progress of the current phase and its open tasks, which can be ticked off in
  place. *Openen* (or a click on a phase) opens the task page.
- **Task page**: a timeline with *Alle fases* and the phases on top; per
  phase the tasks with their subtasks to tick off, options on/off, *Fase
  afronden* / *Heropenen*. Filters *Enkel open* and *Uitgezette opties*;
  *Lijst* opens the phase tasks as a standard list.

## Automations

- A phase milestone is reached as soon as all its active main tasks are done
  (a phase reached by hand stays reached).
- All subtasks done → main task done; ticking a main task ticks its subtasks;
  reopening a subtask reopens its main task.
- Milestone and task deadlines follow the project's start and end date.
