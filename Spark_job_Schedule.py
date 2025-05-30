# -*- coding: utf-8 -*-
"""Spark_job_scheduling.ipynb

"""

from fractions import Fraction

# ====================================================
# Simulation Core Classes and Functions
# ====================================================

class App:
    def __init__(self, id, duration, deadline):
        self.id = id
        self.duration = duration               # Required processing time
        self.nominalRate = Fraction(1, duration) # Rate of progress per time unit
        self.deadline = deadline               # Deadline (time units)

    def __repr__(self):
        return "app" + str(self.id)

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        return self.id == other.id

class Scheduler:
    def addProgress(self, running, time):
        raise Exception("Not Implemented")

class Spark:
    def __init__(self, scheduler, running={}, ended={}):
        self.running = dict(running)
        self.ended = dict(ended)
        self.scheduler = scheduler

    def schedule(self, app, time):
        if app in self.running or app in self.ended:
            return self

        all_apps = list(self.running.keys()) + list(self.ended.keys())
        for a in all_apps:
            if a.id == app.id - 1:
                break
        else:
            return self

        running = dict(self.running)
        running[app] = (time, Fraction(0))
        return Spark(self.scheduler, running, self.ended)

    def tick(self, time):
        if not self.running:
            return self

        running = dict(self.running)
        ended = dict(self.ended)
        self.scheduler.addProgress(running, time)

        for app, value in list(running.items()):
            if value[1] >= 1:
                ended[app] = (value[0], time)
        for app in ended:
            if app in running:
                del running[app]

        return Spark(self.scheduler, running, ended)

    def error(self, apps):
        eA = Fraction(0)
        eD = Fraction(0)
        for app, value in self.ended.items():
            exec_time = self.ended[app][1] - self.ended[app][0]
            e = Fraction(app.deadline - exec_time, app.deadline)
            if e < 0:
                eD += -e
            else:
                eA += e
        n = len(apps)
        return (float(eA) / n, float(eD) / n) if n > 0 else (0.0, 0.0)

    

    def computeUnfeasibility(self, apps, steps):
        for app in apps:
            if app not in self.ended and app not in self.running:
                return True
            if app in self.running and (self.running[app][0] + app.duration > steps):
                return True
        return False

    def computeScenarioViolations(self, apps, steps):
        if self.computeViolations(apps, steps) or self.computeUnfeasibility(apps, steps):
            return False
        for app in apps:
            if app not in self.ended and app in self.running:
                if self.running[app][0] + app.duration <= steps:
                    return True
        return False

    def computeNonViolations(self, apps, steps):
        return (not self.computeViolations(apps, steps) and
                not self.computeScenarioViolations(apps, steps) and
                not self.computeUnfeasibility(apps, steps))

    def __eq__(self, other):
        return self.running == other.running and self.ended == other.ended

    def __hash__(self):
        return hash(self.__repr__())

    def __repr__(self):
        return "r:%s, e:%s" % (self.running, self.ended)

def nextStates(apps, state, time):
    if not apps:
        return {state}
    app = apps[0]
    state_sched = state.schedule(app, time)
    return nextStates(apps[1:], state_sched, time) | nextStates(apps[1:], state, time)

def simulate(initial, apps, steps):
    states = {initial}
    for t in range(0, steps + 1):
        newStates = set()
        for state in states:
            newStates |= nextStates(apps, state.tick(t), t)
        states = newStates
    return states

def computeMetrics(states, apps, steps):
    total_turnaround = 0
    total_waiting = 0
    count_tasks = 0
    on_time_tasks = 0

    for state in states:
        for app in apps:
            if app in state.ended:
                sub_time, finish_time = state.ended[app]
                turnaround = finish_time - sub_time
                waiting = max(0, turnaround - app.duration)
                total_turnaround += turnaround
                total_waiting += waiting
                count_tasks += 1
                if turnaround <= app.deadline:
                    on_time_tasks += 1

    avg_turnaround = total_turnaround / count_tasks if count_tasks else 0
    avg_waiting = total_waiting / count_tasks if count_tasks else 0
    deadline_adherence = (on_time_tasks / count_tasks * 100) if count_tasks else 0

    eA_total = sum(state.error(apps)[0] for state in states) / len(states) * 100
    eD_total = sum(state.error(apps)[1] for state in states) / len(states) * 100

    violations_pct = (len([s for s in states if s.computeViolations(apps, steps)]) / len(states)) * 100
    scenario_violations_pct = (len([s for s in states if s.computeScenarioViolations(apps, steps)]) / len(states)) * 100
    unfeasibles_pct = (len([s for s in states if s.computeUnfeasibility(apps, steps)]) / len(states)) * 100
    non_violations_pct = (len([s for s in states if s.computeNonViolations(apps, steps)]) / len(states)) * 100

    metrics = {
        "avg_turnaround_time": avg_turnaround,
        "avg_waiting_time": avg_waiting,
        "deadline_adherence_pct": deadline_adherence,
        "eA_pct": eA_total,
        "eD_pct": eD_total,
        "violations_pct": violations_pct,
        "scenario_violations_pct": scenario_violations_pct,
        "unfeasibles_pct": unfeasibles_pct,
        "non_violations_pct": non_violations_pct,
        "num_states": len(states),
        "num_tasks": count_tasks
    }
    return metrics

# ====================================================
# Scheduler Implementations
# ====================================================

class FIFO(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        first_app = min(running.keys(), key=lambda app: running[app][0])
        running[first_app] = (running[first_app][0], running[first_app][1] + first_app.nominalRate)

class Fair(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        cnt = len(running)
        for app in running:
            running[app] = (running[app][0], running[app][1] + app.nominalRate / cnt)

class EDFAll(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        for app in running:
            running[app] = (running[app][0], running[app][1] + app.nominalRate)

class EDFPure(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        earliest_app = min(running.keys(), key=lambda app: app.deadline)
        running[earliest_app] = (running[earliest_app][0], running[earliest_app][1] + earliest_app.nominalRate)

class RoundRobin(Scheduler):
    def __init__(self, time_slice):
        self.time_slice = time_slice
        self.last_index = -1

    def addProgress(self, running, time):
        apps_list = list(running.keys())
        if not apps_list:
            return
        self.last_index = (self.last_index + 1) % len(apps_list)
        app = apps_list[self.last_index]
        running[app] = (running[app][0], running[app][1] + app.nominalRate * self.time_slice)

class ShortestJobNext(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        shortest_app = min(running.keys(), key=lambda app: app.duration)
        running[shortest_app] = (running[shortest_app][0], running[shortest_app][1] + shortest_app.nominalRate)

class LeastLaxityFirst(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        def laxity(app):
            remaining_time = 1 - running[app][1]
            return (app.deadline - time) - remaining_time
        least_lax_app = min(running.keys(), key=laxity)
        running[least_lax_app] = (running[least_lax_app][0], running[least_lax_app][1] + least_lax_app.nominalRate)

class PriorityScheduler(Scheduler):
    def __init__(self, priorities):
        self.priorities = priorities

    def addProgress(self, running, time):
        if not running:
            return
        highest_priority_app = max(running.keys(), key=lambda app: self.priorities[app])
        running[highest_priority_app] = (running[highest_priority_app][0], running[highest_priority_app][1] + highest_priority_app.nominalRate)

class MultilevelFeedbackQueue(Scheduler):
    def __init__(self, num_queues, time_slices):
        self.num_queues = num_queues
        self.time_slices = time_slices
        self.queues = [[] for _ in range(num_queues)]
        self.app_queue = {}

    def addProgress(self, running, time):
        if not running:
            return

        # Synchronize queues with running apps
        # Remove apps from queues if they're no longer in running
        for app in list(self.app_queue.keys()):
            if app not in running:
                queue_idx = self.app_queue[app]
                if app in self.queues[queue_idx]:
                    self.queues[queue_idx].remove(app)
                del self.app_queue[app]

        # Add new running apps to the highest priority queue
        for app in running:
            if app not in self.app_queue:
                self.queues[0].append(app)
                self.app_queue[app] = 0

        # Process one app from the highest non-empty queue
        for i in range(self.num_queues):
            if self.queues[i]:
                app = self.queues[i].pop(0)
                if app in running:  # Ensure app is still in running before updating
                    progress_increment = app.nominalRate * self.time_slices[i]
                    running[app] = (running[app][0], running[app][1] + progress_increment)

                    # If app is not complete, move to next lower-priority queue
                    if running[app][1] < 1:
                        next_queue = min(i + 1, self.num_queues - 1)
                        self.queues[next_queue].append(app)
                        self.app_queue[app] = next_queue
                    else:
                        del self.app_queue[app]  # Remove from tracking if complete
                break

# ====================================================
# Comparative Analysis: Run simulation for each scheduler
# ====================================================

if __name__ == "__main__":
   

    schedulers = [
        ("FIFO", FIFO()),
        ("Fair", Fair()),
        ("EDFAll", EDFAll()),
        ("EDFPure", EDFPure()),
        ("RoundRobin (ts=10)", RoundRobin(time_slice=10)),
        ("ShortestJobNext", ShortestJobNext()),
        ("LeastLaxityFirst", LeastLaxityFirst()),
        ("Priority", PriorityScheduler({apps[0]: 1, apps[1]: 2, apps[2]: 3})),
        ("MultilevelFeedbackQueue", MultilevelFeedbackQueue(num_queues=3, time_slices=[10, 20, 30]))
    ]

    comparative_results = {}

    for name, scheduler in schedulers:
        init = Spark(scheduler, {apps[0]: (1, Fraction(0))}, {})
        final_states = simulate(init, apps, steps)
        metrics = computeMetrics(final_states, apps, steps)
        comparative_results[name] = metrics

        print("Scheduler:", name)
        print(f"  Number of final states: {metrics['num_states']}")
        print(f"  Avg Turnaround Time: {metrics['avg_turnaround_time']:.2f} time units")
        print(f"  Avg Waiting Time: {metrics['avg_waiting_time']:.2f} time units")
        print(f"  Deadline Adherence: {metrics['deadline_adherence_pct']:.1f}%")
        print(f"  eA: {metrics['eA_pct']:.1f}%   eD: {metrics['eD_pct']:.9f}%")
        print(f"  Violations: {metrics['violations_pct']:.1f}%")
        print(f"  Scenario Violations: {metrics['scenario_violations_pct']:.1f}%")
        print(f"  Unfeasibles: {metrics['unfeasibles_pct']:.1f}%")
        print(f"  Non Violations: {metrics['non_violations_pct']:.1f}%")
        print("-" * 40)

    try:
        import pandas as pd
        df = pd.DataFrame.from_dict(comparative_results, orient="index")
        df.index.name = "Scheduler"
        print("\nComparative Analysis Summary:")
        print(df)
    except ImportError:
        pass

from fractions import Fraction

# ====================================================
# Simulation Core Classes and Functions
# ====================================================

class App:
    def __init__(self, id, duration, deadline):
        self.id = id
        self.duration = duration               # Required processing time
        self.nominalRate = Fraction(1, duration) # Rate of progress per time unit
        self.deadline = deadline               # Deadline (time units)

    def __repr__(self):
        return "app" + str(self.id)

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        return self.id == other.id

class Scheduler:
    def addProgress(self, running, time):
        raise Exception("Not Implemented")

class Spark:
    def __init__(self, scheduler, running={}, ended={}):
        self.running = dict(running)
        self.ended = dict(ended)
        self.scheduler = scheduler

    def schedule(self, app, time):
        if app in self.running or app in self.ended:
            return self

        all_apps = list(self.running.keys()) + list(self.ended.keys())
        for a in all_apps:
            if a.id == app.id - 1:
                break
        else:
            return self

        running = dict(self.running)
        running[app] = (time, Fraction(0))
        return Spark(self.scheduler, running, self.ended)

    def tick(self, time):
        if not self.running:
            return self

        running = dict(self.running)
        ended = dict(self.ended)
        self.scheduler.addProgress(running, time)

        for app, value in list(running.items()):
            if value[1] >= 1:
                ended[app] = (value[0], time)
        for app in ended:
            if app in running:
                del running[app]

        return Spark(self.scheduler, running, ended)

    def error(self, apps):
        eA = Fraction(0)
        eD = Fraction(0)
        for app, value in self.ended.items():
            exec_time = self.ended[app][1] - self.ended[app][0]
            e = Fraction(app.deadline - exec_time, app.deadline)
            if e < 0:
                eD += -e
            else:
                eA += e
        n = len(apps)
        return (float(eA) / n, float(eD) / n) if n > 0 else (0.0, 0.0)

    def computeViolations(self, apps, steps):
        for app in apps:
            if app in self.ended:
                if self.ended[app][1] - self.ended[app][0] > app.deadline:
                    return True
        return False

    def computeUnfeasibility(self, apps, steps):
        for app in apps:
            if app not in self.ended and app not in self.running:
                return True
            if app in self.running and (self.running[app][0] + app.duration > steps):
                return True
        return False

    def computeScenarioViolations(self, apps, steps):
        if self.computeViolations(apps, steps) or self.computeUnfeasibility(apps, steps):
            return False
        for app in apps:
            if app not in self.ended and app in self.running:
                if self.running[app][0] + app.duration <= steps:
                    return True
        return False

    def computeNonViolations(self, apps, steps):
        return (not self.computeViolations(apps, steps) and
                not self.computeScenarioViolations(apps, steps) and
                not self.computeUnfeasibility(apps, steps))

    def __eq__(self, other):
        return self.running == other.running and self.ended == other.ended

    def __hash__(self):
        return hash(self.__repr__())

    def __repr__(self):
        return "r:%s, e:%s" % (self.running, self.ended)

def nextStates(apps, state, time):
    if not apps:
        return {state}
    app = apps[0]
    state_sched = state.schedule(app, time)
    return nextStates(apps[1:], state_sched, time) | nextStates(apps[1:], state, time)

def simulate(initial, apps, steps):
    states = {initial}
    for t in range(0, steps + 1):
        newStates = set()
        for state in states:
            newStates |= nextStates(apps, state.tick(t), t)
        states = newStates
    return states

def computeMetrics(states, apps, steps):
    total_turnaround = 0
    total_waiting = 0
    count_tasks = 0
    on_time_tasks = 0

    for state in states:
        for app in apps:
            if app in state.ended:
                sub_time, finish_time = state.ended[app]
                turnaround = finish_time - sub_time
                waiting = max(0, turnaround - app.duration)
                total_turnaround += turnaround
                total_waiting += waiting
                count_tasks += 1
                if turnaround <= app.deadline:
                    on_time_tasks += 1

    avg_turnaround = total_turnaround / count_tasks if count_tasks else 0
    avg_waiting = total_waiting / count_tasks if count_tasks else 0
    deadline_adherence = (on_time_tasks / count_tasks * 100) if count_tasks else 0

    eA_total = sum(state.error(apps)[0] for state in states) / len(states) * 100
    eD_total = sum(state.error(apps)[1] for state in states) / len(states) * 100

    violations_pct = (len([s for s in states if s.computeViolations(apps, steps)]) / len(states)) * 100
    scenario_violations_pct = (len([s for s in states if s.computeScenarioViolations(apps, steps)]) / len(states)) * 100
    unfeasibles_pct = (len([s for s in states if s.computeUnfeasibility(apps, steps)]) / len(states)) * 100
    non_violations_pct = (len([s for s in states if s.computeNonViolations(apps, steps)]) / len(states)) * 100

    metrics = {
        "avg_turnaround_time": avg_turnaround,
        "avg_waiting_time": avg_waiting,
        "deadline_adherence_pct": deadline_adherence,
        "eA_pct": eA_total,
        "eD_pct": eD_total,
        "violations_pct": violations_pct,
        "scenario_violations_pct": scenario_violations_pct,
        "unfeasibles_pct": unfeasibles_pct,
        "non_violations_pct": non_violations_pct,
        "num_states": len(states),
        "num_tasks": count_tasks
    }
    return metrics

# ====================================================
# Scheduler Implementations
# ====================================================

class FIFO(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        first_app = min(running.keys(), key=lambda app: running[app][0])
        running[first_app] = (running[first_app][0], running[first_app][1] + first_app.nominalRate)

class Fair(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        cnt = len(running)
        for app in running:
            running[app] = (running[app][0], running[app][1] + app.nominalRate / cnt)

class EDFAll(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        for app in running:
            running[app] = (running[app][0], running[app][1] + app.nominalRate)

class EDFPure(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        earliest_app = min(running.keys(), key=lambda app: app.deadline)
        running[earliest_app] = (running[earliest_app][0], running[earliest_app][1] + earliest_app.nominalRate)

class RoundRobin(Scheduler):
    def __init__(self, time_slice):
        self.time_slice = time_slice
        self.last_index = -1

    def addProgress(self, running, time):
        apps_list = list(running.keys())
        if not apps_list:
            return
        self.last_index = (self.last_index + 1) % len(apps_list)
        app = apps_list[self.last_index]
        running[app] = (running[app][0], running[app][1] + app.nominalRate * self.time_slice)

class ShortestJobNext(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        shortest_app = min(running.keys(), key=lambda app: app.duration)
        running[shortest_app] = (running[shortest_app][0], running[shortest_app][1] + shortest_app.nominalRate)

class LeastLaxityFirst(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        def laxity(app):
            remaining_time = 1 - running[app][1]
            return (app.deadline - time) - remaining_time
        least_lax_app = min(running.keys(), key=laxity)
        running[least_lax_app] = (running[least_lax_app][0], running[least_lax_app][1] + least_lax_app.nominalRate)

class PriorityScheduler(Scheduler):
    def __init__(self, priorities):
        self.priorities = priorities

    def addProgress(self, running, time):
        if not running:
            return
        highest_priority_app = max(running.keys(), key=lambda app: self.priorities[app])
        running[highest_priority_app] = (running[highest_priority_app][0], running[highest_priority_app][1] + highest_priority_app.nominalRate)

class MultilevelFeedbackQueue(Scheduler):
    def __init__(self, num_queues, time_slices):
        self.num_queues = num_queues
        self.time_slices = time_slices
        self.queues = [[] for _ in range(num_queues)]
        self.app_queue = {}

    def addProgress(self, running, time):
        if not running:
            return

        # Synchronize queues with running apps
        # Remove apps from queues if they're no longer in running
        for app in list(self.app_queue.keys()):
            if app not in running:
                queue_idx = self.app_queue[app]
                if app in self.queues[queue_idx]:
                    self.queues[queue_idx].remove(app)
                del self.app_queue[app]

        # Add new running apps to the highest priority queue
        for app in running:
            if app not in self.app_queue:
                self.queues[0].append(app)
                self.app_queue[app] = 0

        # Process one app from the highest non-empty queue
        for i in range(self.num_queues):
            if self.queues[i]:
                app = self.queues[i].pop(0)
                if app in running:  # Ensure app is still in running before updating
                    progress_increment = app.nominalRate * self.time_slices[i]
                    running[app] = (running[app][0], running[app][1] + progress_increment)

                    # If app is not complete, move to next lower-priority queue
                    if running[app][1] < 1:
                        next_queue = min(i + 1, self.num_queues - 1)
                        self.queues[next_queue].append(app)
                        self.app_queue[app] = next_queue
                    else:
                        del self.app_queue[app]  # Remove from tracking if complete
                break

# ====================================================
# Comparative Analysis: Run simulation for each scheduler
# ====================================================

if __name__ == "__main__":
    scale = 1
    
    steps = 720 // scale  # Restored to 720 for meaningful simulation

    schedulers = [
        ("FIFO", FIFO()),
        ("Fair", Fair()),
        ("EDFAll", EDFAll()),
        ("EDFPure", EDFPure()),
        ("RoundRobin (ts=10)", RoundRobin(time_slice=10)),
        ("ShortestJobNext", ShortestJobNext()),
        ("LeastLaxityFirst", LeastLaxityFirst()),
        ("Priority", PriorityScheduler({apps[0]: 1, apps[1]: 2, apps[2]: 3})),
        ("MultilevelFeedbackQueue", MultilevelFeedbackQueue(num_queues=3, time_slices=[10, 20, 30]))
    ]

    comparative_results = {}

    for name, scheduler in schedulers:
        init = Spark(scheduler, {apps[0]: (1, Fraction(0))}, {})
        final_states = simulate(init, apps, steps)
        metrics = computeMetrics(final_states, apps, steps)
        comparative_results[name] = metrics

        print("Scheduler:", name)
        print(f"  Number of final states: {metrics['num_states']}")
        print(f"  Avg Turnaround Time: {metrics['avg_turnaround_time']:.2f} time units")
        print(f"  Avg Waiting Time: {metrics['avg_waiting_time']:.2f} time units")
        print(f"  Deadline Adherence: {metrics['deadline_adherence_pct']:.1f}%")
        print(f"  eA: {metrics['eA_pct']:.1f}%   eD: {metrics['eD_pct']:.9f}%")
        print(f"  Violations: {metrics['violations_pct']:.1f}%")
        print(f"  Scenario Violations: {metrics['scenario_violations_pct']:.1f}%")
        print(f"  Unfeasibles: {metrics['unfeasibles_pct']:.1f}%")
        print(f"  Non Violations: {metrics['non_violations_pct']:.1f}%")
        print("-" * 40)

    try:
        import pandas as pd
        df = pd.DataFrame.from_dict(comparative_results, orient="index")
        df.index.name = "Scheduler"
        print("\nComparative Analysis Summary:")
        print(df)
    except ImportError:
        pass

from fractions import Fraction

# ====================================================
# Simulation Core Classes and Functions
# ====================================================

class App:
    def __init__(self, id, duration, deadline):
        self.id = id
        self.duration = duration               # Required processing time
        self.nominalRate = Fraction(1, duration) # Rate of progress per time unit
        self.deadline = deadline               # Deadline (time units)

    def __repr__(self):
        return "app" + str(self.id)

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        return self.id == other.id

class Scheduler:
    def addProgress(self, running, time):
        raise Exception("Not Implemented")

class Spark:
    def __init__(self, scheduler, running={}, ended={}):
        self.running = dict(running)
        self.ended = dict(ended)
        self.scheduler = scheduler

    def schedule(self, app, time):
        if app in self.running or app in self.ended:
            return self

        all_apps = list(self.running.keys()) + list(self.ended.keys())
        for a in all_apps:
            if a.id == app.id - 1:
                break
        else:
            return self

        running = dict(self.running)
        running[app] = (time, Fraction(0))
        return Spark(self.scheduler, running, self.ended)

    def tick(self, time):
        if not self.running:
            return self

        running = dict(self.running)
        ended = dict(self.ended)
        self.scheduler.addProgress(running, time)

        for app, value in list(running.items()):
            if value[1] >= 1:
                ended[app] = (value[0], time)
        for app in ended:
            if app in running:
                del running[app]

        return Spark(self.scheduler, running, ended)

    def error(self, apps):
        eA = Fraction(0)
        eD = Fraction(0)
        for app, value in self.ended.items():
            exec_time = self.ended[app][1] - self.ended[app][0]
            e = Fraction(app.deadline - exec_time, app.deadline)
            if e < 0:
                eD += -e
            else:
                eA += e
        n = len(apps)
        return (float(eA) / n, float(eD) / n) if n > 0 else (0.0, 0.0)

    def computeViolations(self, apps, steps):
        for app in apps:
            if app in self.ended:
                if self.ended[app][1] - self.ended[app][0] > app.deadline:
                    return True
        return False

    def computeUnfeasibility(self, apps, steps):
        for app in apps:
            if app not in self.ended and app not in self.running:
                return True
            if app in self.running and (self.running[app][0] + app.duration > steps):
                return True
        return False

    def computeScenarioViolations(self, apps, steps):
        if self.computeViolations(apps, steps) or self.computeUnfeasibility(apps, steps):
            return False
        for app in apps:
            if app not in self.ended and app in self.running:
                if self.running[app][0] + app.duration <= steps:
                    return True
        return False

    def computeNonViolations(self, apps, steps):
        return (not self.computeViolations(apps, steps) and
                not self.computeScenarioViolations(apps, steps) and
                not self.computeUnfeasibility(apps, steps))

    def __eq__(self, other):
        return self.running == other.running and self.ended == other.ended

    def __hash__(self):
        return hash(self.__repr__())

    def __repr__(self):
        return "r:%s, e:%s" % (self.running, self.ended)

def nextStates(apps, state, time):
    if not apps:
        return {state}
    app = apps[0]
    state_sched = state.schedule(app, time)
    return nextStates(apps[1:], state_sched, time) | nextStates(apps[1:], state, time)

def simulate(initial, apps, steps):
    states = {initial}
    for t in range(0, steps + 1):
        newStates = set()
        for state in states:
            newStates |= nextStates(apps, state.tick(t), t)
        states = newStates
    return states

def computeMetrics(states, apps, steps):
    total_turnaround = 0
    total_waiting = 0
    count_tasks = 0
    on_time_tasks = 0

    for state in states:
        for app in apps:
            if app in state.ended:
                sub_time, finish_time = state.ended[app]
                turnaround = finish_time - sub_time
                waiting = max(0, turnaround - app.duration)
                total_turnaround += turnaround
                total_waiting += waiting
                count_tasks += 1
                if turnaround <= app.deadline:
                    on_time_tasks += 1

    avg_turnaround = total_turnaround / count_tasks if count_tasks else 0
    avg_waiting = total_waiting / count_tasks if count_tasks else 0
    deadline_adherence = (on_time_tasks / count_tasks * 100) if count_tasks else 0

    eA_total = sum(state.error(apps)[0] for state in states) / len(states) * 100
    eD_total = sum(state.error(apps)[1] for state in states) / len(states) * 100

    violations_pct = (len([s for s in states if s.computeViolations(apps, steps)]) / len(states)) * 100
    scenario_violations_pct = (len([s for s in states if s.computeScenarioViolations(apps, steps)]) / len(states)) * 100
    unfeasibles_pct = (len([s for s in states if s.computeUnfeasibility(apps, steps)]) / len(states)) * 100
    non_violations_pct = (len([s for s in states if s.computeNonViolations(apps, steps)]) / len(states)) * 100

    metrics = {
        "avg_turnaround_time": avg_turnaround,
        "avg_waiting_time": avg_waiting,
        "deadline_adherence_pct": deadline_adherence,
        "eA_pct": eA_total,
        "eD_pct": eD_total,
        "violations_pct": violations_pct,
        "scenario_violations_pct": scenario_violations_pct,
        "unfeasibles_pct": unfeasibles_pct,
        "non_violations_pct": non_violations_pct,
        "num_states": len(states),
        "num_tasks": count_tasks
    }
    return metrics

# ====================================================
# Scheduler Implementations
# ====================================================

class FIFO(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        first_app = min(running.keys(), key=lambda app: running[app][0])
        running[first_app] = (running[first_app][0], running[first_app][1] + first_app.nominalRate)

class Fair(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        cnt = len(running)
        for app in running:
            running[app] = (running[app][0], running[app][1] + app.nominalRate / cnt)

class EDFAll(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        for app in running:
            running[app] = (running[app][0], running[app][1] + app.nominalRate)

class EDFPure(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        earliest_app = min(running.keys(), key=lambda app: app.deadline)
        running[earliest_app] = (running[earliest_app][0], running[earliest_app][1] + earliest_app.nominalRate)

class RoundRobin(Scheduler):
    def __init__(self, time_slice):
        self.time_slice = time_slice
        self.last_index = -1

    def addProgress(self, running, time):
        apps_list = list(running.keys())
        if not apps_list:
            return
        self.last_index = (self.last_index + 1) % len(apps_list)
        app = apps_list[self.last_index]
        running[app] = (running[app][0], running[app][1] + app.nominalRate * self.time_slice)

class ShortestJobNext(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        shortest_app = min(running.keys(), key=lambda app: app.duration)
        running[shortest_app] = (running[shortest_app][0], running[shortest_app][1] + shortest_app.nominalRate)

class LeastLaxityFirst(Scheduler):
    def addProgress(self, running, time):
        if not running:
            return
        def laxity(app):
            remaining_time = 1 - running[app][1]
            return (app.deadline - time) - remaining_time
        least_lax_app = min(running.keys(), key=laxity)
        running[least_lax_app] = (running[least_lax_app][0], running[least_lax_app][1] + least_lax_app.nominalRate)

class PriorityScheduler(Scheduler):
    def __init__(self, priorities):
        self.priorities = priorities

    def addProgress(self, running, time):
        if not running:
            return
        highest_priority_app = max(running.keys(), key=lambda app: self.priorities[app])
        running[highest_priority_app] = (running[highest_priority_app][0], running[highest_priority_app][1] + highest_priority_app.nominalRate)

class MultilevelFeedbackQueue(Scheduler):
    def __init__(self, num_queues, time_slices):
        self.num_queues = num_queues
        self.time_slices = time_slices
        self.queues = [[] for _ in range(num_queues)]
        self.app_queue = {}

    def addProgress(self, running, time):
        if not running:
            return

        # Synchronize queues with running apps
        # Remove apps from queues if they're no longer in running
        for app in list(self.app_queue.keys()):
            if app not in running:
                queue_idx = self.app_queue[app]
                if app in self.queues[queue_idx]:
                    self.queues[queue_idx].remove(app)
                del self.app_queue[app]

        # Add new running apps to the highest priority queue
        for app in running:
            if app not in self.app_queue:
                self.queues[0].append(app)
                self.app_queue[app] = 0

        # Process one app from the highest non-empty queue
        for i in range(self.num_queues):
            if self.queues[i]:
                app = self.queues[i].pop(0)
                if app in running:  # Ensure app is still in running before updating
                    progress_increment = app.nominalRate * self.time_slices[i]
                    running[app] = (running[app][0], running[app][1] + progress_increment)

                    # If app is not complete, move to next lower-priority queue
                    if running[app][1] < 1:
                        next_queue = min(i + 1, self.num_queues - 1)
                        self.queues[next_queue].append(app)
                        self.app_queue[app] = next_queue
                    else:
                        del self.app_queue[app]  # Remove from tracking if complete
                break

# ====================================================
# Comparative Analysis: Run simulation for each scheduler
# ====================================================

if __name__ == "__main__":
  

    schedulers = [
        ("FIFO", FIFO()),
        ("Fair", Fair()),
        ("EDFAll", EDFAll()),
        ("EDFPure", EDFPure()),
        ("RoundRobin (ts=10)", RoundRobin(time_slice=10)),
        ("ShortestJobNext", ShortestJobNext()),
        ("LeastLaxityFirst", LeastLaxityFirst()),
        ("Priority", PriorityScheduler({apps[0]: 1, apps[1]: 2, apps[2]: 3})),
        ("MultilevelFeedbackQueue", MultilevelFeedbackQueue(num_queues=3, time_slices=[10, 20, 30]))
    ]

    comparative_results = {}

    for name, scheduler in schedulers:
        init = Spark(scheduler, {apps[0]: (1, Fraction(0))}, {})
        final_states = simulate(init, apps, steps)
        metrics = computeMetrics(final_states, apps, steps)
        comparative_results[name] = metrics

        print("Scheduler:", name)
        print(f"  Number of final states: {metrics['num_states']}")
        print(f"  Avg Turnaround Time: {metrics['avg_turnaround_time']:.2f} time units")
        print(f"  Avg Waiting Time: {metrics['avg_waiting_time']:.2f} time units")
        print(f"  Deadline Adherence: {metrics['deadline_adherence_pct']:.1f}%")
        print(f"  eA: {metrics['eA_pct']:.1f}%   eD: {metrics['eD_pct']:.9f}%")
        print(f"  Violations: {metrics['violations_pct']:.1f}%")
        print(f"  Scenario Violations: {metrics['scenario_violations_pct']:.1f}%")
        print(f"  Unfeasibles: {metrics['unfeasibles_pct']:.1f}%")
        print(f"  Non Violations: {metrics['non_violations_pct']:.1f}%")
        print("-" * 40)

    try:
        import pandas as pd
        df = pd.DataFrame.from_dict(comparative_results, orient="index")
        df.index.name = "Scheduler"
        print("\nComparative Analysis Summary:")
        print(df)
    except ImportError:
        pass
