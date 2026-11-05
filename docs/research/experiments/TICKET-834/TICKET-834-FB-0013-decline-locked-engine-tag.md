# FB-0013 · decline (a product feature, not a hypothesis)

*Runner: Harshad · Ruler: Pawan · Shared rules: [`_common.md`](_common.md)*

**The claim (T-001):** a locked engine tag per day: "engine read at your first trade".

**Declined as a pre-registration.** It asks Scope to *show* which engine version read each day, not to test anything about trading. It matches the spec's own promise that "a trader may be shown the hash" (§2). It depends on:
- methodology Rule 3 (schemas versioned by file, not by edit);
- the framework being locked, so there is a hash to show;
- TD-011, for any regime-dependent read it would stamp.

**Route:** an engineering ticket after the framework lock, gated on Rule 3 and TD-011.

**Ruling (Pawan):** ______ · date ______
