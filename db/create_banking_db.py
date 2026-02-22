"""
Generate a realistic sample banking SQLite database for the Ensō Banking Agent.

Tables:
  customers        – 60 customers with demographics
  accounts         – ~120 accounts (checking, savings, money-market, CD)
  transactions     – ~3 000 transactions spanning 2024-01 → 2026-02
  loans            – ~40 loans (mortgage, auto, personal, student, home-equity)
  cards            – ~70 debit/credit cards
  fraud_alerts     – ~25 fraud/suspicious-activity alerts
  branches         – 10 branch locations
  customer_support – ~45 support tickets

Run:  python create_banking_db.py
Produces: banking.db in the same directory.
"""

import sqlite3, random, datetime, pathlib, os

random.seed(42)

DB_PATH = pathlib.Path(__file__).with_name("banking.db")

# ── helpers ───────────────────────────────────────────────────────────
def rand_date(start: str, end: str) -> str:
    s = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    return str(s + datetime.timedelta(days=random.randint(0, (e - s).days)))

def rand_phone():
    return f"({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"

def rand_ssn_last4():
    return f"{random.randint(1000,9999)}"

def rand_email(first, last):
    domains = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "hotmail.com"]
    return f"{first.lower()}.{last.lower()}@{random.choice(domains)}"

# ── seed data ─────────────────────────────────────────────────────────
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes",
]
STATES = ["GA", "NC", "SC", "FL", "TN", "AL", "VA", "TX", "CA", "NY", "IL", "OH", "PA"]
CITIES_BY_STATE = {
    "GA": ["Atlanta", "Marietta", "Savannah", "Augusta", "Alpharetta"],
    "NC": ["Charlotte", "Raleigh", "Durham", "Greensboro", "Asheville"],
    "SC": ["Charleston", "Columbia", "Greenville", "Myrtle Beach"],
    "FL": ["Miami", "Orlando", "Tampa", "Jacksonville", "Naples"],
    "TN": ["Nashville", "Memphis", "Knoxville", "Chattanooga"],
    "AL": ["Birmingham", "Huntsville", "Montgomery", "Mobile"],
    "VA": ["Richmond", "Virginia Beach", "Arlington", "Norfolk"],
    "TX": ["Houston", "Dallas", "Austin", "San Antonio"],
    "CA": ["Los Angeles", "San Francisco", "San Diego", "San Jose"],
    "NY": ["New York", "Buffalo", "Albany", "Rochester"],
    "IL": ["Chicago", "Springfield", "Naperville", "Peoria"],
    "OH": ["Columbus", "Cleveland", "Cincinnati", "Dayton"],
    "PA": ["Philadelphia", "Pittsburgh", "Harrisburg", "Allentown"],
}
ACCOUNT_TYPES = ["Checking", "Savings", "Money Market", "Certificate of Deposit"]
LOAN_TYPES = ["Mortgage", "Auto", "Personal", "Student", "Home Equity"]
CARD_TYPES = ["Debit", "Credit"]
CARD_NETWORKS = ["Visa", "Mastercard", "Amex"]
TX_CATEGORIES = [
    "Groceries", "Dining", "Gas", "Utilities", "Rent/Mortgage", "Insurance",
    "Healthcare", "Entertainment", "Shopping", "Travel", "Transfer", "ATM Withdrawal",
    "Direct Deposit", "Payroll", "Refund", "Subscription", "Education", "Charity",
]
TX_MERCHANTS = {
    "Groceries": ["Kroger", "Publix", "Whole Foods", "Trader Joe's", "Aldi", "Costco"],
    "Dining": ["Starbucks", "Chick-fil-A", "Olive Garden", "Chipotle", "Waffle House", "McDonald's"],
    "Gas": ["Shell", "BP", "Chevron", "QuikTrip", "RaceTrac"],
    "Utilities": ["Georgia Power", "AT&T", "Comcast", "Duke Energy", "Spectrum"],
    "Rent/Mortgage": ["Truist Mortgage", "Greystar", "Cortland Apts", "MAA Communities"],
    "Insurance": ["State Farm", "Allstate", "GEICO", "Progressive"],
    "Healthcare": ["CVS Pharmacy", "Walgreens", "Emory Healthcare", "Kaiser Permanente"],
    "Entertainment": ["Netflix", "Spotify", "AMC Theatres", "Disney+", "Hulu"],
    "Shopping": ["Amazon", "Target", "Walmart", "Best Buy", "Home Depot", "Nordstrom"],
    "Travel": ["Delta Air Lines", "Marriott", "Hilton", "Uber", "Lyft", "Airbnb"],
    "Transfer": ["Zelle Transfer", "Venmo", "Wire Transfer", "Internal Transfer"],
    "ATM Withdrawal": ["ATM – Truist", "ATM – Wells Fargo", "ATM – Chase"],
    "Direct Deposit": ["Employer Payroll", "ADP Direct Deposit", "Gusto Payroll"],
    "Payroll": ["Employer Payroll", "ADP Direct Deposit"],
    "Refund": ["Amazon Refund", "Target Refund", "Credit Card Refund"],
    "Subscription": ["Apple iCloud", "YouTube Premium", "Adobe Creative Cloud", "Microsoft 365"],
    "Education": ["Coursera", "Udemy", "Georgia Tech Tuition", "Student Loan Payment"],
    "Charity": ["Red Cross", "United Way", "Habitat for Humanity"],
}
FRAUD_TYPES = [
    "Suspicious ATM withdrawal", "Unusual international transaction",
    "Card-not-present fraud", "Multiple rapid purchases", "Account takeover attempt",
    "Phishing-related activity", "Duplicate transaction detected",
    "Large wire transfer flagged", "Unusual login location",
]
SUPPORT_TOPICS = [
    "Account inquiry", "Lost/stolen card", "Dispute transaction", "Loan inquiry",
    "Online banking issue", "Fee reversal request", "Address change",
    "Wire transfer assistance", "Statement request", "Fraud report",
]
BRANCH_DATA = [
    ("Main Street Branch", "100 Main St", "Atlanta", "GA", "30301"),
    ("Peachtree Center Branch", "225 Peachtree St NE", "Atlanta", "GA", "30303"),
    ("Buckhead Branch", "3344 Peachtree Rd NE", "Atlanta", "GA", "30326"),
    ("Midtown Branch", "1100 Peachtree St NE", "Atlanta", "GA", "30309"),
    ("Charlotte Uptown Branch", "401 S Tryon St", "Charlotte", "NC", "28202"),
    ("Raleigh Downtown Branch", "150 Fayetteville St", "Raleigh", "NC", "27601"),
    ("Nashville Broadway Branch", "315 Broadway", "Nashville", "TN", "37201"),
    ("Miami Brickell Branch", "801 Brickell Ave", "Miami", "FL", "33131"),
    ("Orlando Colonial Branch", "2100 E Colonial Dr", "Orlando", "FL", "32803"),
    ("Richmond Main Branch", "919 E Main St", "Richmond", "VA", "23219"),
]

# ── build DB ──────────────────────────────────────────────────────────
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.executescript("PRAGMA journal_mode=WAL;")

# Drop existing tables
for t in ["customer_support", "fraud_alerts", "transactions", "cards", "loans", "accounts", "customers", "branches"]:
    cur.execute(f"DROP TABLE IF EXISTS {t}")

# ── branches ──────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE branches (
    branch_id     INTEGER PRIMARY KEY,
    branch_name   TEXT NOT NULL,
    address       TEXT,
    city          TEXT,
    state         TEXT,
    zip_code      TEXT,
    phone         TEXT,
    manager_name  TEXT,
    opened_date   TEXT
)""")
for i, (name, addr, city, st, zc) in enumerate(BRANCH_DATA, 1):
    cur.execute("INSERT INTO branches VALUES (?,?,?,?,?,?,?,?,?)",
                (i, name, addr, city, st, zc, rand_phone(),
                 f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                 rand_date("2005-01-01", "2020-12-31")))

# ── customers ─────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
    date_of_birth TEXT,
    ssn_last4     TEXT,
    address       TEXT,
    city          TEXT,
    state         TEXT,
    zip_code      TEXT,
    member_since  TEXT,
    credit_score  INTEGER,
    annual_income REAL,
    branch_id     INTEGER REFERENCES branches(branch_id),
    status        TEXT DEFAULT 'Active'
)""")

customers = []
for cid in range(1, 61):
    fn = random.choice(FIRST_NAMES)
    ln = random.choice(LAST_NAMES)
    st = random.choice(STATES)
    city = random.choice(CITIES_BY_STATE[st])
    customers.append(cid)
    cur.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        cid, fn, ln, rand_email(fn, ln), rand_phone(),
        rand_date("1955-01-01", "2002-12-31"), rand_ssn_last4(),
        f"{random.randint(100,9999)} {random.choice(['Oak','Pine','Elm','Maple','Cedar','Peach','Magnolia'])} "
        f"{random.choice(['St','Ave','Blvd','Dr','Ln','Way'])}",
        city, st, f"{random.randint(10000,99999)}",
        rand_date("2010-01-01", "2025-06-30"),
        random.randint(580, 850),
        round(random.uniform(28000, 250000), 2),
        random.randint(1, 10),
        random.choice(["Active"] * 9 + ["Inactive"]),  # 90 % active
    ))

# ── accounts ──────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE accounts (
    account_id    INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    account_type  TEXT NOT NULL,
    account_number TEXT UNIQUE,
    routing_number TEXT DEFAULT '061000104',
    balance       REAL NOT NULL,
    interest_rate REAL,
    opened_date   TEXT,
    status        TEXT DEFAULT 'Open'
)""")

acct_id = 0
account_ids = []  # (account_id, customer_id, account_type, balance)
for cid in customers:
    # everyone gets checking + savings; some get more
    types_for_cust = ["Checking", "Savings"]
    if random.random() < 0.3:
        types_for_cust.append(random.choice(["Money Market", "Certificate of Deposit"]))
    for atype in types_for_cust:
        acct_id += 1
        if atype == "Checking":
            bal = round(random.uniform(200, 25000), 2)
            rate = 0.01
        elif atype == "Savings":
            bal = round(random.uniform(500, 80000), 2)
            rate = round(random.uniform(0.5, 4.5), 2)
        elif atype == "Money Market":
            bal = round(random.uniform(5000, 150000), 2)
            rate = round(random.uniform(3.0, 5.0), 2)
        else:  # CD
            bal = round(random.uniform(10000, 200000), 2)
            rate = round(random.uniform(4.0, 5.5), 2)
        acct_num = f"1{random.randint(100000000, 999999999)}"
        account_ids.append((acct_id, cid, atype, bal))
        cur.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?)", (
            acct_id, cid, atype, acct_num, "061000104",
            bal, rate, rand_date("2010-01-01", "2025-12-31"),
            random.choice(["Open"] * 19 + ["Closed"]),
        ))

# ── transactions ──────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE transactions (
    transaction_id   INTEGER PRIMARY KEY,
    account_id       INTEGER NOT NULL REFERENCES accounts(account_id),
    transaction_date TEXT NOT NULL,
    post_date        TEXT,
    description      TEXT,
    category         TEXT,
    amount           REAL NOT NULL,
    transaction_type TEXT CHECK(transaction_type IN ('credit','debit')),
    balance_after    REAL,
    reference_number TEXT,
    channel          TEXT
)""")

tx_id = 0
channels = ["Online", "Mobile App", "Branch", "ATM", "POS", "ACH", "Wire"]
for aid, cid, atype, bal in account_ids:
    if atype in ("Certificate of Deposit",):
        n_tx = random.randint(2, 6)  # few for CDs
    else:
        n_tx = random.randint(30, 70)
    running = bal
    for _ in range(n_tx):
        tx_id += 1
        cat = random.choice(TX_CATEGORIES)
        merchant = random.choice(TX_MERCHANTS[cat])
        tx_date = rand_date("2024-01-01", "2026-02-18")

        if cat in ("Direct Deposit", "Payroll", "Refund"):
            tx_type = "credit"
            amt = round(random.uniform(500, 6000), 2)
        elif cat == "Transfer":
            tx_type = random.choice(["credit", "debit"])
            amt = round(random.uniform(50, 3000), 2)
        else:
            tx_type = "debit"
            amt = round(random.uniform(3, 1500), 2)

        if tx_type == "credit":
            running = round(running + amt, 2)
        else:
            running = round(running - amt, 2)

        post_date = str(datetime.date.fromisoformat(tx_date) + datetime.timedelta(days=random.randint(0, 2)))
        ref = f"REF{random.randint(10000000, 99999999)}"
        cur.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            tx_id, aid, tx_date, post_date, merchant, cat,
            amt, tx_type, running, ref, random.choice(channels),
        ))

# ── loans ─────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE loans (
    loan_id          INTEGER PRIMARY KEY,
    customer_id      INTEGER NOT NULL REFERENCES customers(customer_id),
    loan_type        TEXT NOT NULL,
    principal_amount REAL NOT NULL,
    interest_rate    REAL,
    term_months      INTEGER,
    monthly_payment  REAL,
    remaining_balance REAL,
    origination_date TEXT,
    maturity_date    TEXT,
    status           TEXT DEFAULT 'Active',
    collateral       TEXT
)""")

borrowers = random.sample(customers, 35)
loan_id = 0
for cid in borrowers:
    n_loans = random.choices([1, 2], weights=[75, 25])[0]
    for _ in range(n_loans):
        loan_id += 1
        ltype = random.choice(LOAN_TYPES)
        if ltype == "Mortgage":
            principal = round(random.uniform(150000, 650000), 2)
            rate = round(random.uniform(5.5, 7.5), 2)
            term = random.choice([180, 240, 360])
            collateral = "Primary residence"
        elif ltype == "Auto":
            principal = round(random.uniform(15000, 65000), 2)
            rate = round(random.uniform(4.5, 9.0), 2)
            term = random.choice([36, 48, 60, 72])
            collateral = f"{random.randint(2020,2026)} {random.choice(['Toyota Camry','Honda Accord','Ford F-150','Chevy Equinox','Tesla Model 3','BMW X5','Hyundai Tucson'])}"
        elif ltype == "Personal":
            principal = round(random.uniform(3000, 35000), 2)
            rate = round(random.uniform(7.0, 15.0), 2)
            term = random.choice([12, 24, 36, 48, 60])
            collateral = None
        elif ltype == "Student":
            principal = round(random.uniform(10000, 120000), 2)
            rate = round(random.uniform(4.0, 8.0), 2)
            term = random.choice([120, 180, 240])
            collateral = None
        else:  # Home Equity
            principal = round(random.uniform(25000, 150000), 2)
            rate = round(random.uniform(6.0, 9.0), 2)
            term = random.choice([60, 120, 180])
            collateral = "Primary residence (HELOC)"

        monthly = round(principal * (rate / 100 / 12) / (1 - (1 + rate / 100 / 12) ** (-term)), 2)
        orig = rand_date("2018-01-01", "2025-12-31")
        mat = str(datetime.date.fromisoformat(orig) + datetime.timedelta(days=term * 30))
        remaining = round(principal * random.uniform(0.3, 0.98), 2)
        status = random.choice(["Active"] * 8 + ["Paid Off", "Delinquent"])
        if status == "Paid Off":
            remaining = 0.0

        cur.execute("INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            loan_id, cid, ltype, principal, rate, term,
            monthly, remaining, orig, mat, status, collateral,
        ))

# ── cards ─────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE cards (
    card_id         INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    account_id      INTEGER REFERENCES accounts(account_id),
    card_type       TEXT NOT NULL,
    card_network    TEXT,
    card_number_last4 TEXT,
    expiration_date TEXT,
    credit_limit    REAL,
    current_balance REAL,
    reward_points   INTEGER DEFAULT 0,
    issued_date     TEXT,
    status          TEXT DEFAULT 'Active'
)""")

card_id = 0
for cid in customers:
    # each customer gets 1-3 cards
    n_cards = random.choices([1, 2, 3], weights=[40, 40, 20])[0]
    cust_accounts = [a for a in account_ids if a[1] == cid]
    for _ in range(n_cards):
        card_id += 1
        ctype = random.choice(CARD_TYPES)
        network = random.choice(CARD_NETWORKS)
        last4 = f"{random.randint(1000,9999)}"
        exp = f"{random.randint(2026,2030):04d}-{random.randint(1,12):02d}"
        if ctype == "Credit":
            limit = round(random.choice([2000, 5000, 7500, 10000, 15000, 25000, 50000]), 2)
            cur_bal = round(random.uniform(0, limit * 0.7), 2)
            link_acct = None
        else:
            limit = None
            cur_bal = None
            link_acct = cust_accounts[0][0] if cust_accounts else None
        rewards = random.randint(0, 85000) if ctype == "Credit" else 0
        cur.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            card_id, cid, link_acct, ctype, network, last4, exp,
            limit, cur_bal, rewards,
            rand_date("2018-01-01", "2025-12-31"),
            random.choice(["Active"] * 9 + ["Blocked", "Expired"]),
        ))

# ── fraud_alerts ──────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE fraud_alerts (
    alert_id       INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    account_id     INTEGER REFERENCES accounts(account_id),
    card_id        INTEGER REFERENCES cards(card_id),
    alert_date     TEXT NOT NULL,
    alert_type     TEXT,
    description    TEXT,
    amount         REAL,
    merchant       TEXT,
    location       TEXT,
    status         TEXT DEFAULT 'Open',
    resolution     TEXT,
    resolved_date  TEXT
)""")

alert_id = 0
for _ in range(25):
    alert_id += 1
    cid = random.choice(customers)
    cust_accts = [a[0] for a in account_ids if a[1] == cid]
    aid = random.choice(cust_accts) if cust_accts else None
    atype = random.choice(FRAUD_TYPES)
    status = random.choice(["Open", "Under Review", "Resolved", "Resolved", "Closed"])
    alert_date = rand_date("2024-06-01", "2026-02-18")
    res_date = None
    resolution = None
    if status in ("Resolved", "Closed"):
        res_date = str(datetime.date.fromisoformat(alert_date) + datetime.timedelta(days=random.randint(1, 14)))
        resolution = random.choice([
            "Confirmed fraud – card replaced", "False positive – customer verified",
            "Transaction reversed", "Account locked and reset",
            "Customer contacted – legitimate transaction",
        ])
    locations = ["Atlanta, GA", "New York, NY", "London, UK", "Lagos, NG", "São Paulo, BR",
                 "Toronto, CA", "Online", "Unknown"]
    cur.execute("INSERT INTO fraud_alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        alert_id, cid, aid, None, alert_date, atype,
        f"{atype} detected on account",
        round(random.uniform(50, 8000), 2),
        random.choice(["Amazon", "Wire Transfer", "ATM", "Unknown Vendor", "Forex Exchange"]),
        random.choice(locations), status, resolution, res_date,
    ))

# ── customer_support ──────────────────────────────────────────────────
cur.execute("""
CREATE TABLE customer_support (
    ticket_id     INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    topic         TEXT,
    subject       TEXT,
    description   TEXT,
    priority      TEXT CHECK(priority IN ('Low','Medium','High','Critical')),
    status        TEXT DEFAULT 'Open',
    channel       TEXT,
    created_date  TEXT,
    resolved_date TEXT,
    assigned_to   TEXT
)""")

ticket_id = 0
support_channels = ["Phone", "Online Chat", "Email", "Branch", "Mobile App"]
for _ in range(45):
    ticket_id += 1
    cid = random.choice(customers)
    topic = random.choice(SUPPORT_TOPICS)
    created = rand_date("2024-06-01", "2026-02-18")
    status = random.choice(["Open", "In Progress", "Resolved", "Resolved", "Closed"])
    res = None
    if status in ("Resolved", "Closed"):
        res = str(datetime.date.fromisoformat(created) + datetime.timedelta(days=random.randint(0, 7)))
    cur.execute("INSERT INTO customer_support VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
        ticket_id, cid, topic,
        f"{topic} – Customer #{cid}",
        f"Customer contacted regarding {topic.lower()}. Details recorded by agent.",
        random.choice(["Low", "Medium", "Medium", "High", "Critical"]),
        status, random.choice(support_channels), created, res,
        f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
    ))

conn.commit()

# ── summary ───────────────────────────────────────────────────────────
print(f"Database created: {DB_PATH}")
for table in ["branches", "customers", "accounts", "transactions", "loans", "cards", "fraud_alerts", "customer_support"]:
    cnt = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:20s} → {cnt:>5,} rows")

conn.close()
print("\nDone ✓")
