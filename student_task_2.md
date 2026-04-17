# Your task

> Your mission, should you choose to accept it...

## Aim - Agentic Robot System 

We enhance the remote controlled litter detection robot. The robot now should be controlled by an agentic system and interact with a human companion.

- Build a (Multi-) Agent System that controls the robot and interact with a human controller.
- The robot should be able to search litter in a predefined square space like an open field. 
- Detected litter should be marked on a map and reported to a human. The human collects the litter, later.

Reminder:

- Document the process and usage of AI during the lab task

Assumptions/Given Functions:

- The robot has a self localisation and reports its position and orientation.
- Consider the robot as blackbox, that can be controlled via messages and reports sensor information and its status via messages.
- Assume the starting point of the robot is one corner of the open field. Within this field there are no possible collisions.

```
  OPEN FIELD
  +------------------------------------------------------------------+
  |                                                                  |
  |   SEARCH ZONE                                                    |
  |   +--------------------------------------------------------+     |
  |   | [R]---->---->---->---->---->---->---->---->---->----v  |     |
  |   |  |   *              *                      *        |  |     |
  |   |  ^<----<----<----<----<----<----<----<----<----<----+  |     |
  |   |  |           *                    *                    |     |
  |   |  +---->---->---->---->---->---->---->---->---->----v   |     |
  |   |      *                  *                   *    |     |     |
  |   |  ^<----<----<----<----<----<----<----<----<----<-+     |     |
  |   |  |                *                                    |     |
  |   |  +---->---->---->---->---->---->---->---->---->-[END]  |     |
  |   +--------------------------------------------------------+     |
  |                                                                  |
  +------------------------------------------------------------------+

  [R]  = Robot Start        * = Detected Litter
  ----> = Search Path       Boustrophedon (lawnmower) pattern
```

### Work Packages

1. Layout the agents you need and define the task they need to do. 
2. Decide about the connection between robot and agents.
3. Think about the concurrent task that might be active, the movement pattern, how to start and stop the robot, interaction with a human.
4. Research solutions to achieve your functionality (e.g. Speech processing)
5. Integrate the Robot to your agentic system.

Questions you might ask yourself:

- Which component should plan the scenario?
- Which component observes the current execution?
- How is a plan represented?

## Deliverable

1. AI Usage: How did you use AI during this task? (Prompts, Agents, Pipelines, Tools, ...)
2. Illustration of the agentic architecture. 
3. Demo litter search with agentic interaction.

## Kickstart idea for a first simple system

A first simple system might look like this:

1. After the start the robot just turns on the spot and captures images.
2. In case it detects litter the robot stops and sits down.
3. After some seconds the robot stands up and continues with 1

## Guardrails
