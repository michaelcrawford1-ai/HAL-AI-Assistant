# Case Study: Getting the Build System Off the GUI

When I started coordinating several AI agents on this project, I was the integration layer. I triggered each planning session, carried state between tools when the rails did not reach, decided when to run an audit, and walked every change through review to merge by hand. It worked, but I was the bottleneck, and that per-step overhead became the dominant cost of making progress.

My first instinct was to automate the thing in front of me: the desktop UI. A few attempts, mostly a daemon that typed into the app's composer, fixed specific failures but the underlying surface was structurally fragile. The content view was opaque to automation, the daemon could never confirm that a submission actually landed, and a class of silent-failure bugs kept reappearing. I was hardening something that did not want to be hardened.

The decision in ADR-008 was to stop automating the GUI and move the connective tissue off it entirely. Every agent already had a command-line or SDK path that did not touch the desktop. GitHub was already the source of truth for the work. So the orchestrator became a small service that dispatches each agent in its native environment, keeps canonical state in GitHub, and uses Discord as the surface where it talks to me.

The part I was most careful about is what it is not allowed to do. It never merges on its own. It cannot act on the house, so it cannot unlock a door or disable an alarm; those route through a separate safety gate. Every agent call is logged with secrets stripped before the row is written. Hard caps keep it from looping without bound, and each automated lane has to earn trust against the manual version before it is allowed to take over.

The tradeoff I accepted was one more always-on service to operate, plus new failure modes around auth and polling. What I optimized for was getting myself out of the loop on the routine steps without giving up the final say on anything that is hard to undo.
