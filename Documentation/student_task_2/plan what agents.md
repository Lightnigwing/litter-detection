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

# Was für Funktionen brauchen wir:
- mithilfe der kamera melden wenn müll gefunden
- herausfinden wo der müll liegt (map)
- map aus eigener odometry aufbauen
- position auf der map wiesen
- movmentbefehle an den hund schicken
