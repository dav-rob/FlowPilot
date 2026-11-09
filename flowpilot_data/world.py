"""In-memory enterprise world for one partition, plus synthetic entity factories."""
from __future__ import annotations

import re
from typing import Any

from .schema import TABLES
from .util import Rng, ago, day, digest, sub_rng
from . import vocab


class World:
    def __init__(self, seed: int, partition: str):
        self.seed, self.partition = seed, partition
        self.rng = sub_rng(seed, partition, "world")
        self.tables: dict[str, list[dict]] = {t: [] for t in TABLES}
        self.index: dict[str, tuple[str, dict]] = {}
        self._ctr = 0
        self._names: set[str] = set()
        self._domains: set[str] = set()
        self._emails: set[str] = set()

    # -- ids -------------------------------------------------------------
    def new_id(self, prefix: str, length: int = 8) -> str:
        while True:
            self._ctr += 1
            rid = f"{prefix}-{digest(self.seed, self.partition, prefix, self._ctr)[:length].upper()}"
            if rid not in self.index:
                return rid

    def add(self, table: str, rid: str | None = None, **fields: Any) -> dict:
        rid = rid or self.new_id(TABLES[table][0])
        rec = {"id": rid, **fields}
        self.tables[table].append(rec)
        self.index[rid] = (table, rec)
        return rec

    def get(self, rid: str) -> dict:
        return self.index[rid][1]

    def table_of(self, rid: str) -> str:
        return self.index[rid][0]

    def unique_name(self, make, rng: Rng | None = None, stem: int = 0) -> str:
        for i in range(60):
            n = make()
            if i >= 30:  # plain name space is crowded: disambiguate with an initial / locality
                n = n.replace(" ", f" {(rng or self.rng).choice('ABCDEFGHJKLMNPRSTW')}. ", 1) if "Ltd" not in n and "LLP" not in n and "Limited" not in n else f"{n} ({(rng or self.rng).pick(vocab.TOWNS)})"
            key = " ".join(n.split()[:stem]).lower() if stem else n
            if key not in self._names:
                self._names.add(key)
                return n
        raise RuntimeError("name space exhausted")

    # -- identifiers with clearly synthetic formats ------------------------
    def sort_code(self, rng: Rng) -> str:
        return f"00-{rng.digits(2)}-{rng.digits(2)}"  # 00-xx-xx: synthetic, not a real bank range

    def account_number(self, rng: Rng) -> str:
        return "9" + rng.digits(7)

    def iban(self, sort_code: str, acct: str) -> str:
        return f"GB00SYNT{sort_code.replace('-', '')}{acct}"  # check digits 00 => deliberately invalid

    def phone(self, rng: Rng) -> str:
        return rng.pick([f"020 7946 0{rng.digits(3)}", f"0161 496 0{rng.digits(3)}", f"07700 900{rng.digits(3)}"])

    def postcode(self, rng: Rng) -> str:
        return f"ZZ{rng.randrange(1, 9)} {rng.randrange(1, 9)}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}"

    def unique_email(self, local: str, rng: Rng, domain: str = "mail.example") -> str:
        e = f"{local}@{domain}"
        while e in self._emails:
            e = f"{local}{rng.randrange(2, 99)}@{domain}"
        self._emails.add(e)
        return e

    def person(self, rng: Rng) -> tuple[str, str]:
        return rng.pick(vocab.FIRST), rng.pick(vocab.LAST)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------------------------------------------------------------------------
# Entity factories. Each creates linked, coherent records; callers override fields.
# ---------------------------------------------------------------------------

def mk_employee(w: World, rng: Rng, dept: str | None = None, status: str = "active", **over) -> dict:
    name = over["name"] if "name" in over else w.unique_name(lambda: " ".join(w.person(rng)), rng)
    f, l = name.split(" ", 1)[0], name.split(" ")[-1]
    user = slug(name).replace("-", ".")
    rec = dict(name=name, email=f"{user}@{vocab.COMPANY['domain']}", username=user.split(".")[0][0] + user.split(".")[-1],
               department=dept or rng.pick(vocab.DEPARTMENTS), job_title=rng.pick(["Analyst", "Manager", "Team Lead", "Engineer", "Head of Function"]),
               status=status, start_date=day(rng.randrange(200, 2500)), manager_id=None)
    rec.update(over)
    return w.add("employees", **rec)


def mk_supplier(w: World, rng: Rng, **over) -> dict:
    name = over.pop("name", None) or w.unique_name(lambda: f"{rng.pick(vocab.SUP_A)} {rng.pick(vocab.SUP_B)} {rng.pick(vocab.SUFFIX)}", rng, stem=2)
    base = slug(name.rsplit(" ", 1)[0] if name.split()[-1] in vocab.SUFFIX else name).replace("-", "")
    if base in w._domains:
        base += rng.digits(2)
    w._domains.add(base)
    rec = dict(name=name, trading_names=[], status="active", onboarded_on=day(rng.randrange(120, 2000)),
               vat_number=f"GB000{rng.digits(6)}", company_number=f"ZZ{rng.digits(6)}", email_domain=f"{base}.example",
               address=f"{rng.randrange(2, 120)} {rng.pick(vocab.STREETS)}, {rng.pick(vocab.TOWNS)} {w.postcode(rng)}",
               payment_terms_days=rng.pick([14, 30, 45]), category=rng.pick(vocab.SUP_B), onboarding_checks="complete",
               active_bank_account_id=None, owner_employee_id=None, notes="")
    rec.update(over)
    return w.add("suppliers", **rec)


def mk_bank(w: World, rng: Rng, supplier: dict, status: str = "active", since_days: int | None = None, **over) -> dict:
    sc, an = w.sort_code(rng), w.account_number(rng)
    rec = dict(supplier_id=supplier["id"], account_name=supplier["name"], sort_code=sc, account_number=an,
               iban=w.iban(sc, an), status=status, bank_name="Fictional Bank plc (synthetic)",
               added_on=day(since_days if since_days is not None else rng.randrange(200, 1500)))
    rec.update(over)
    b = w.add("supplier_bank_accounts", **rec)
    if status == "active" and supplier.get("active_bank_account_id") is None:
        supplier["active_bank_account_id"] = b["id"]
    return b


def mk_contact(w: World, rng: Rng, supplier: dict, authorised: bool = True, **over) -> dict:
    f, l = w.person(rng)
    rec = dict(supplier_id=supplier["id"], name=f"{f} {l}", email=f"{f.lower()}.{l.lower()}@{supplier['email_domain']}",
               phone=w.phone(rng), role=rng.pick(["Accounts Receivable", "Finance Director", "Credit Controller"]),
               authorised_for_bank_changes=authorised, verified_on=day(rng.randrange(30, 700)), status="active")
    rec.update(over)
    return w.add("supplier_contacts", **rec)


def mk_system(w: World, rng: Rng, **over) -> dict:
    name = over.pop("name", None) or w.unique_name(lambda: f"{rng.pick(vocab.SYSTEM_STEMS)}{rng.pick(vocab.SYSTEM_SUFFIX)}", rng)
    rec = dict(name=name, aliases=[], description=f"{name} application supporting {rng.pick(vocab.BUSINESS_UNITS)}",
               business_unit=rng.pick(vocab.BUSINESS_UNITS), data_classification=rng.pick(["internal", "confidential", "customer_pii"]),
               hosting=rng.pick(["on_premises", "cloud"]), criticality=rng.pick(["tier_3", "tier_2", "tier_1"]),
               lifecycle="live", owner_employee_id=None, privileged_access_review_days=rng.randrange(20, 80))
    rec.update(over)
    return w.add("systems", **rec)


def mk_database(w: World, rng: Rng, system: dict, **over) -> dict:
    rec = dict(system_id=system["id"], name=f"{system['name'].lower()}_{rng.pick(['main', 'ledger', 'archive', 'audit'])}",
               engine=rng.pick(["PostgreSQL 15", "Oracle 19c", "SQL Server 2019"]),
               facts=dict(encrypted_at_rest=True, encryption_key_age_days=rng.randrange(20, 300), log_retention_days=rng.pick([400, 450, 500]),
                          last_backup_hours=rng.randrange(2, 30), customer_pii_tables=rng.randrange(0, 9), row_count=rng.randrange(10_000, 9_000_000)))
    facts = over.pop("facts", {})
    rec.update(over)
    rec["facts"].update(facts)
    return w.add("databases", **rec)


def mk_customer(w: World, rng: Rng, **over) -> dict:
    name = over.pop("full_name", None) or w.unique_name(lambda: " ".join(w.person(rng)), rng)
    rec = dict(full_name=name, date_of_birth=f"{rng.randrange(1948, 2002)}-{rng.randrange(1, 13):02d}-{rng.randrange(1, 28):02d}",
               email=w.unique_email(f"{slug(name).replace('-', '.')}", rng), phone=w.phone(rng), postcode=w.postcode(rng),
               address=f"{rng.randrange(1, 99)} {rng.pick(vocab.STREETS)}, {rng.pick(vocab.TOWNS)}",
               customer_reference=f"C{rng.digits(8)}", ni_number=f"QQ {rng.digits(2)} {rng.digits(2)} {rng.digits(2)} C",
               status="active", previous_names=[], created_on=day(rng.randrange(100, 3000)), flags=[])
    rec.update(over)
    return w.add("customers", **rec)


def mk_contract(w: World, rng: Rng, supplier: dict, **over) -> dict:
    n = rng.randrange(1, 4)
    rec = dict(supplier_id=supplier["id"], counterparty_name=supplier["name"], contract_number=f"AGR-{rng.digits(5)}",
               title=f"{supplier['category']} agreement", status="draft", owner_employee_id=None,
               annual_value_gbp=rng.choice([24_000, 85_000, 180_000, 420_000, 950_000]), term_months=rng.choice([12, 24, 36]),
               current_version_id=None, processes_personal_data=False, criticality="standard", start_date=day(-rng.randrange(5, 60)))
    rec.update(over)
    return w.add("contracts", **rec)


def mk_cmdb(w: World, rng: Rng, **over) -> dict:
    host = over.pop("hostname", None) or f"hl{rng.pick(['app', 'db', 'web', 'bat'])}{rng.digits(3)}"
    rec = dict(hostname=host, asset_tag=f"AT{rng.digits(6)}", serial_number=f"SN{rng.hex(8)}",
               ip_address=f"10.{rng.randrange(10, 99)}.{rng.randrange(0, 250)}.{rng.randrange(2, 250)}", mac_address=":".join(rng.hex(2) for _ in range(6)),
               asset_type=rng.pick(["server", "virtual_machine", "laptop", "network_device"]), status="in_service", environment=rng.pick(["prod", "uat", "dev"]),
               owner_id=None, system_id=None, last_seen=ago(rng.randrange(0, 3), rng=rng), description="", location=rng.pick(["DC-East", "DC-West", "Office-Eastbridge"]))
    rec.update(over)
    return w.add("cmdb_items", **rec)


def mk_log(w: World, rng: Rng, subject_id: str, summary: str, actor: str, when: str, action: str = "update", **extra) -> dict:
    return w.add("audit_log", subject_id=subject_id, summary=summary, actor=actor, timestamp=when, action=action, **extra)


def background(w: World, rng: Rng, n_scale: int) -> dict[str, list[dict]]:
    """Background population: employees, systems, suppliers and customers unrelated to scenario facts (noise/ambiguity)."""
    out = {"employees": [mk_employee(w, rng) for _ in range(8 + n_scale)]}
    sups = [mk_supplier(w, rng) for _ in range(6 + n_scale)]
    for s in sups:
        b = mk_bank(w, rng, s)
        mk_contact(w, rng, s)
        s["owner_employee_id"] = rng.pick(out["employees"])["id"]
        mk_log(w, rng, s["id"], "Supplier record reviewed", rng.pick(out["employees"])["id"], ago(rng.randrange(40, 400), rng=rng), "review")
    out["suppliers"] = sups
    out["customers"] = [mk_customer(w, rng) for _ in range(6 + n_scale)]
    out["systems"] = []
    for _ in range(4 + n_scale // 2):
        s = mk_system(w, rng, owner_employee_id=rng.pick(out["employees"])["id"])
        mk_database(w, rng, s)
        out["systems"].append(s)
    return out
