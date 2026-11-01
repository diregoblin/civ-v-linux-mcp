"""Social policies, ideology, religion, research and stolen techs.

One of the civ5 MCP server's tool modules: every tool here registers on the server in
harness/mcp_server.py, which keeps the game handle, the guard and the tool sets (see its docstring).
"""
from __future__ import annotations

from harness import mcp_server as core
from harness.mcp_server import J, guarded, retired


@retired
@guarded
def available_policies() -> str:
    """Social policies: what is adopted, what can be adopted right now (enum + name; the effect text is
    in reference("policies")), which branches are unlocked / unlockable, culture vs next cost. Use before
    choose_policy / unlock_policy_branch. Each adoptable policy carries `call` (choose_policy), each unlockable branch its unlock_policy_branch (#47).
    `ideologies` is the ideology choice (#145): per ideology the met civs that follow it (friend / denounced_us /
    we_denounced / at_war), and from the ideologies' era on, while no ideology is chosen, free_tenets_on_adopt
    (the early-adopter bonus) and the tier-1 `tenets` with their text; before that era a row is `locked` with its
    `era` (#179). `ideology` is mine, and while the engine asks for the choice each row carries its
    choose_ideology `call`."""
    return J(core.game().available_policies())


@retired
@guarded
def choose_policy(policy: str) -> str:
    """Adopt a social policy, e.g. POLICY_TRADITION, within an already-unlocked branch."""
    return J(core.game().choose_policy(policy))


@retired
@guarded
def unlock_policy_branch(branch: str) -> str:
    """Unlock a policy branch/tree, e.g. POLICY_BRANCH_TRADITION, spending a culture policy slot."""
    return J(core.game().unlock_policy_branch(branch))


@retired
@guarded
def choose_ideology(branch: str) -> str:
    """Choose the empire's ideology when ENDTURN_BLOCKING_CHOOSE_IDEOLOGY is up (3 Factories or the Modern
    era): branch is POLICY_BRANCH_FREEDOM, POLICY_BRANCH_ORDER or POLICY_BRANCH_AUTOCRACY. Irreversible
    short of a revolution. Other civs' ideologies are public (their choice matters for ideological
    pressure/unhappiness). Returns `ideology` (confirmed) and `free_tenets` to spend via choose_policy."""
    return J(core.game().choose_ideology(branch))


@retired
@guarded
def free_great_person_options() -> str:
    """When turn_status shows ENDTURN_BLOCKING_FREE_ITEMS: how many free Great People are owed and which unit
    types (UNIT_SCIENTIST, UNIT_ENGINEER, UNIT_MERCHANT, UNIT_ARTIST, UNIT_WRITER, UNIT_MUSICIAN, ...) qualify;
    `answers` the choose_free_great_person rows."""
    return J(core.game().free_great_person_options())


@retired
@guarded
def choose_free_great_person(unit: str) -> str:
    """Claim a free Great Person, e.g. unit="UNIT_SCIENTIST". Only valid while turn_status shows
    ENDTURN_BLOCKING_FREE_ITEMS (e.g. right after completing the Liberty policy tree)."""
    return J(core.game().choose_free_great_person(unit))


@retired
@guarded
def religion_overview() -> str:
    """Religion Overview screen: faith, next Great Prophet threshold, my pantheon/religion and beliefs, all founded
    religions with their beliefs and city counts, per own city the followers and pressure of each religion, and
    `auto_purchase`: the automatic faith purchase pull-down (current selection and every option it lists with
    its faith cost; change it with set_faith_purchase)."""
    return J(core.game().religion_overview())


@retired
@guarded
def set_faith_purchase(kind: str, index: int = 0) -> str:
    """The Religion Overview's automatic faith purchase pull-down. `kind` is nothing, save_prophet,
    unit or building; `index` is the unit/building id from religion_overview().auto_purchase.options
    (each option lists its faith cost). Refused for anything the pull-down does not currently list."""
    return J(core.game().set_faith_purchase(kind, index))


@retired
@guarded
def change_ideology() -> str:
    """The policy screen's Switch Ideology button: adopt the preferred ideology public opinion pushes
    toward, at the cost overview().public_opinion.switch_cost shows (anarchy turns, tenets kept).
    Refused while the button is grey (no public-opinion unhappiness)."""
    return J(core.game().change_ideology())


@retired
@guarded
def faith_great_person_options() -> str:
    """When turn_status shows ENDTURN_BLOCKING_FAITH_GREAT_PERSON: the Great People the faith can buy now;
    `answers` the choose_faith_great_person rows."""
    return J(core.game().faith_great_person_options())


@retired
@guarded
def choose_faith_great_person(unit: str) -> str:
    """Take one unit type from faith_great_person_options (it appears in the capital or holy city)."""
    return J(core.game().choose_faith_great_person(unit))


@retired
@guarded
def available_beliefs(kind: str) -> str:
    """Beliefs still available for one slot (enum + name; what each does is in reference("beliefs")). kind: pantheon | founder | follower | enhancer |
    bonus | reformation. Founding a religion takes pantheon(if none yet)/founder/follower(/bonus for Byzantium);
    enhancing takes follower + enhancer. kind=founder also lists the religions nobody has founded. A pantheon or reformation belief carries `call` (#47)."""
    return J(core.game().available_beliefs(kind))


@retired
@guarded
def add_reformation_belief(belief: str) -> str:
    """When turn_status shows ENDTURN_BLOCKING_ADD_REFORMATION_BELIEF (Piety's Reformation policy): pick one
    from available_beliefs(kind="reformation")."""
    return J(core.game().add_reformation_belief(belief))


@retired
@guarded
def found_pantheon(belief: str) -> str:
    """Found a pantheon with the given belief, e.g. BELIEF_GOD_OF_THE_SEA. Check turn_status first: only
    valid when blocking_name is ENDTURN_BLOCKING_FOUND_PANTHEON."""
    return J(core.game().found_pantheon(belief))



def _city_xy(g, city, city_x, city_y):
    """(x, y) of the city an order names -- by `city` (its id, as every other city order takes it; GitLab #103) or by
    city_x / city_y -- or a refusal dict."""
    if city is not None:
        rows = g.cities()
        for c in rows if isinstance(rows, list) else []:
            if isinstance(c, dict) and c.get("id") == city:
                return int(c["x"]), int(c["y"])
        return {"ok": False, "err": f"no city of mine with id {city} (state(what='cities') lists them)"}
    if city_x is None or city_y is None:
        return {"ok": False, "err": "name the city: city (its id) or city_x and city_y"}
    return int(city_x), int(city_y)

@retired
@guarded
def found_religion(religion: str, beliefs: list[str], city_x: int | None = None, city_y: int | None = None,
                   custom_name: str = "", city: int | None = None) -> str:
    """Found a religion (RELIGION_..., see available_beliefs(kind="founder").religions) in the city at
    (city_x, city_y) = data1, data2 of the pending BUTTONPOPUP_FOUND_RELIGION. `beliefs` in order: a pantheon
    belief (only if I have no pantheon yet), a founder belief, a follower belief (+ a bonus belief for Byzantium).
    Only valid when blocking_name is ENDTURN_BLOCKING_FOUND_RELIGION. custom_name renames the religion
    (empty keeps the stock name)."""
    g = core.game()
    at = _city_xy(g, city, city_x, city_y)
    if isinstance(at, dict):
        return J(at)
    return J(g.found_religion(religion, beliefs, at[0], at[1], custom_name))


@retired
@guarded
def enhance_religion(religion: str, belief4: str, belief5: str, city_x: int | None = None, city_y: int | None = None,
                     custom_name: str = "", city: int | None = None) -> str:
    """Enhance my founded religion: belief4 = a follower belief, belief5 = an enhancer belief (available_beliefs),
    in the city at (city_x, city_y) = data1, data2 of the pending BUTTONPOPUP_FOUND_RELIGION (the holy city, where
    the Great Prophet stands); custom_name is ignored unless the game asks for one. Only valid when
    blocking_name is ENDTURN_BLOCKING_ENHANCE_RELIGION."""
    g = core.game()
    at = _city_xy(g, city, city_x, city_y)
    if isinstance(at, dict):
        return J(at)
    return J(g.enhance_religion(religion, belief4, belief5, at[0], at[1], custom_name))


@retired
@guarded
def available_research() -> str:
    """Techs I can research right now (prereqs met). `current` marks the one already selected;
    `progress` is the science already stored in a tech (shown whenever it is nonzero).
    `unlocks` is the tech-tree button row for this seat: our units and buildings (not another
    civ's uniques), revealed resources, and the ability the button names (embark, ocean, embassy). Each row carries `call`, its set_research row (#47)."""
    return J(core.game().available_research())


@retired
@guarded
def tech_tree() -> str:
    """The tech tree: `have` (already researched), `techs` (current / available / unavailable with
    prereqs and missing steps, turns-if-researchable, and `unlocks` — the buttons on that tech for
    this seat). No rival column: an embassy shows a capital, not a tech list (the steal-tech chooser
    is the only stock screen that names a rival's techs). available_research is the leaf list only."""
    return J(core.game().tech_tree())


@retired
@guarded
def steal_tech_options() -> str:
    """When a spy finished stealing: which civs I can take a tech from and the techs available from each.
    Each victim carries `player_id` -- pass that to steal_tech. Also listed on turn_status.todo.steal_tech even if blocking_name is still
    POLICY/PRODUCTION/etc. (the engine reports one blocker at a time)."""
    return J(core.game().steal_tech_options())


@retired
@guarded
def steal_tech(tech: str, player_id: int) -> str:
    """Take a stolen tech (TECH_...) from `player_id` (steal_tech_options lists each victim and the
    techs available from it). Clears ENDTURN_BLOCKING_STEAL_TECH."""
    return J(core.game().steal_tech(tech, player_id))


@retired
@guarded
def set_research(tech: str) -> str:
    """Choose current research, e.g. TECH_POTTERY, TECH_MINING, TECH_BRONZE_WORKING. Also the way to claim a
    free technology (blocking_name ENDTURN_BLOCKING_FREE_TECH, e.g. Oxford University): the named tech is
    granted outright (`granted`), current research is left as it was. A tech whose prerequisites are
    missing works like clicking it in the tech tree: the game researches the first missing step now and
    queues the rest (`goal`, `queue` in the reply)."""
    return J(core.game().set_research(tech))
