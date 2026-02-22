"""
Generate a comprehensive sample bank policy PDF for the Enso Banking Agent.
Produces: bank_policies.pdf in the same directory.
"""

from fpdf import FPDF
import pathlib

PDF_PATH = pathlib.Path(__file__).with_name("bank_policies.pdf")


class PolicyPDF(FPDF):
    BLUE = (24, 60, 120)
    DARK = (30, 30, 30)
    GRAY = (80, 80, 80)
    LIGHT_BG = (240, 245, 250)

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*self.BLUE)
        self.cell(0, 8, "Enso National Bank  |  Customer Policy Handbook", align="R")
        self.ln(4)
        self.set_draw_color(*self.BLUE)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 10, f"Enso National Bank - Confidential  |  Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, num, title):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*self.BLUE)
        self.cell(0, 10, f"Section {num}: {title}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*self.DARK)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.GRAY)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.GRAY)
        self.set_x(self.l_margin + 6)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 6, 5.5, "- " + text)

    def table_row(self, cells, bold=False):
        style = "B" if bold else ""
        col_w = (190 - 4) / len(cells)
        self.set_font("Helvetica", style, 9)
        self.set_text_color(*self.DARK)
        for c in cells:
            self.cell(col_w, 6.5, str(c), border=1, align="C")
        self.ln()


pdf = PolicyPDF()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# ─── Cover-ish title ────────────────────────────────────────────────
pdf.ln(20)
pdf.set_font("Helvetica", "B", 28)
pdf.set_text_color(*PolicyPDF.BLUE)
pdf.cell(0, 14, "Enso National Bank", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 16)
pdf.set_text_color(*PolicyPDF.GRAY)
pdf.cell(0, 10, "Customer Policy Handbook", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_font("Helvetica", "I", 11)
pdf.cell(0, 8, "Effective Date: January 1, 2025  |  Version 4.2", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 6, "Approved by the Board of Directors - December 15, 2024", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(10)
pdf.set_draw_color(*PolicyPDF.BLUE)
pdf.set_line_width(0.6)
pdf.line(60, pdf.get_y(), 150, pdf.get_y())
pdf.ln(10)

pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(*PolicyPDF.GRAY)
pdf.multi_cell(0, 5.5,
    "This handbook outlines the policies, procedures, fee schedules, and regulatory guidelines "
    "governing all consumer and small-business banking products offered by Enso National Bank. "
    "All customers, employees, and authorized agents are expected to familiarize themselves with "
    "the contents herein. For questions, contact your branch manager or call 1-800-ENSO-BANK.")

pdf.add_page()

# ══════════════════════════════════════════════════════════════════════
# SECTION 1 - Account Policies
# ══════════════════════════════════════════════════════════════════════
pdf.section_title(1, "Account Policies")

pdf.sub_title("1.1 Account Types")
pdf.body(
    "Enso National Bank offers four primary deposit account types to consumer customers:\n\n"
    "Checking Account: A demand-deposit account designed for everyday transactions including "
    "direct deposits, bill payments, point-of-sale purchases, and ATM withdrawals. No minimum "
    "balance requirement for the Basic Checking tier; Premier Checking requires a $5,000 daily "
    "minimum balance to waive the monthly service fee.\n\n"
    "Savings Account: An interest-bearing deposit account intended for accumulating funds. "
    "Interest is compounded daily and credited monthly. Federal Regulation D limits of six "
    "convenience withdrawals per statement cycle have been permanently lifted per the April 2020 "
    "Federal Reserve interim final rule, but Enso encourages prudent usage.\n\n"
    "Money Market Account: A higher-yield account combining features of checking and savings. "
    "Requires a $5,000 minimum opening deposit. Includes check-writing privileges (up to three "
    "checks per month) and a tiered interest rate structure.\n\n"
    "Certificate of Deposit (CD): A time-deposit product with fixed terms ranging from 3 months "
    "to 60 months. Offers the highest guaranteed annual percentage yield (APY). Early withdrawal "
    "penalties apply (see Section 2 - Fee Schedule)."
)

pdf.sub_title("1.2 Account Opening Requirements")
pdf.body("To open an account, applicants must provide:")
for item in [
    "Valid government-issued photo ID (driver's license, passport, or state ID)",
    "Social Security Number or Individual Taxpayer Identification Number",
    "Proof of current residential address (utility bill, lease, or bank statement dated within 60 days)",
    "Minimum opening deposit: Checking $25, Savings $100, Money Market $5,000, CD $1,000",
    "Completed Customer Identification Program (CIP) form per USA PATRIOT Act Section 326",
]:
    pdf.bullet(item)
pdf.ln(3)

pdf.sub_title("1.3 Joint Accounts")
pdf.body(
    "Joint accounts are available with Rights of Survivorship (JTWROS) or as Tenants in Common "
    "(TIC). All joint owners have equal rights to deposit, withdraw, and close the account unless "
    "restricted by court order. Each joint owner must independently satisfy CIP requirements."
)

pdf.sub_title("1.4 Account Closure")
pdf.body(
    "Customers may close an account at any time by visiting a branch, calling customer service, "
    "or submitting a written request. A $25 early closure fee applies if the account is closed "
    "within 90 days of opening. Outstanding checks and pending ACH transactions must clear before "
    "closure. CD accounts closed before maturity are subject to early withdrawal penalties."
)

pdf.sub_title("1.5 Dormant and Inactive Accounts")
pdf.body(
    "Accounts with no customer-initiated activity for 12 consecutive months are classified as "
    "inactive. After 36 months of inactivity, accounts are reclassified as dormant and a $10/month "
    "dormancy fee is assessed. Funds in dormant accounts are escheated to the state of the "
    "customer's last known address per the Uniform Unclaimed Property Act after the dormancy "
    "period specified by that state (typically 3-5 years)."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 2 - Fee Schedule
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(2, "Fee Schedule")

pdf.body(
    "The following fee schedule is effective January 1, 2025 and applies to all consumer deposit "
    "accounts. Enso National Bank reserves the right to modify fees with 30 days' advance written "
    "notice to affected customers."
)

pdf.sub_title("2.1 Monthly Service Fees")
fees_monthly = [
    ("Fee Type", "Basic Checking", "Premier Checking", "Savings", "Money Market"),
    ("Monthly Service Fee", "$0", "$25*", "$5*", "$15*"),
    ("Waiver Condition", "N/A", "$5,000 min balance", "$300 min balance", "$5,000 min balance"),
    ("Paper Statement Fee", "$3", "$0", "$3", "$0"),
]
for i, row in enumerate(fees_monthly):
    pdf.table_row(row, bold=(i == 0))
pdf.ln(2)
pdf.set_font("Helvetica", "I", 8)
pdf.set_text_color(120, 120, 120)
pdf.cell(0, 5, "* Fee waived when the specified minimum daily balance is maintained throughout the statement cycle.")
pdf.ln(6)

pdf.sub_title("2.2 Transaction Fees")
fees_tx = [
    ("Fee Type", "Amount", "Notes"),
    ("Overdraft Fee", "$35 per item", "Max 3 per day; $5 buffer applies"),
    ("NSF / Returned Item", "$35 per item", "Applies to checks and ACH"),
    ("Stop Payment", "$30 per request", "Online or phone"),
    ("Wire Transfer (Domestic)", "$25 outgoing / $15 incoming", "Same-day processing"),
    ("Wire Transfer (International)", "$45 outgoing / $15 incoming", "1-3 business days"),
    ("Cashier's Check", "$10 each", "Free for Premier Checking"),
    ("ATM (non-Enso network)", "$3 per transaction", "Plus owner surcharge"),
    ("Excessive Withdrawal (Savings)", "$10 per occurrence", "Beyond 6 per cycle"),
    ("Account Research Fee", "$25 per hour", "Min 1 hour"),
]
for i, row in enumerate(fees_tx):
    pdf.table_row(row, bold=(i == 0))
pdf.ln(4)

pdf.sub_title("2.3 Card-Related Fees")
fees_card = [
    ("Fee Type", "Amount", "Notes"),
    ("Replacement Debit Card", "$10", "Expedited delivery: +$25"),
    ("Replacement Credit Card", "$0", "Standard; expedited: $25"),
    ("Foreign Transaction Fee", "3% of amount", "Visa/MC international"),
    ("Cash Advance Fee", "$10 or 5%", "Whichever is greater"),
    ("Late Payment Fee (Credit)", "$29 first / $40 subsequent", "Per billing cycle"),
    ("Over-Credit-Limit Fee", "$0", "Waived per CARD Act"),
    ("Returned Payment Fee", "$25", "Insufficient funds on payment"),
]
for i, row in enumerate(fees_card):
    pdf.table_row(row, bold=(i == 0))
pdf.ln(4)

pdf.sub_title("2.4 Early Withdrawal Penalties (CDs)")
fees_cd = [
    ("CD Term", "Penalty"),
    ("3-6 months", "90 days' interest"),
    ("7-12 months", "180 days' interest"),
    ("13-36 months", "270 days' interest"),
    ("37-60 months", "365 days' interest"),
]
for i, row in enumerate(fees_cd):
    pdf.table_row(row, bold=(i == 0))
pdf.ln(4)

# ══════════════════════════════════════════════════════════════════════
# SECTION 3 - Interest Rate Policy
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(3, "Interest Rate Policy")

pdf.sub_title("3.1 Deposit Rate Tiers (Current as of January 2025)")
rates = [
    ("Product", "Balance Tier", "APY"),
    ("Basic Checking", "All balances", "0.01%"),
    ("Premier Checking", "All balances", "0.05%"),
    ("Savings", "< $10,000", "0.50%"),
    ("Savings", "$10,000 - $49,999", "1.25%"),
    ("Savings", "$50,000+", "2.00%"),
    ("Money Market", "< $25,000", "3.25%"),
    ("Money Market", "$25,000 - $99,999", "3.75%"),
    ("Money Market", "$100,000+", "4.25%"),
    ("12-Month CD", "$1,000+", "4.50%"),
    ("24-Month CD", "$1,000+", "4.75%"),
    ("36-Month CD", "$1,000+", "5.00%"),
    ("60-Month CD", "$1,000+", "5.25%"),
]
for i, row in enumerate(rates):
    pdf.table_row(row, bold=(i == 0))
pdf.ln(3)
pdf.body(
    "Interest rates are variable unless stated otherwise (CDs are fixed for the term). The bank "
    "reserves the right to change variable rates at any time. APY assumes interest remains on "
    "deposit for one year. Fees may reduce earnings."
)

pdf.sub_title("3.2 Loan Interest Rates")
loan_rates = [
    ("Loan Type", "Rate Range (APR)", "Term Options"),
    ("Mortgage - 30yr Fixed", "6.25% - 7.25%", "360 months"),
    ("Mortgage - 15yr Fixed", "5.50% - 6.50%", "180 months"),
    ("Mortgage - 5/1 ARM", "5.75% - 6.75%", "360 months"),
    ("Auto Loan (New)", "4.99% - 7.49%", "36-72 months"),
    ("Auto Loan (Used)", "5.49% - 8.99%", "36-60 months"),
    ("Personal Loan", "7.99% - 14.99%", "12-60 months"),
    ("Student Loan (Private)", "4.25% - 7.99%", "60-240 months"),
    ("Home Equity (HELOC)", "Prime + 1.0% - 3.0%", "60-180 months"),
]
for i, row in enumerate(loan_rates):
    pdf.table_row(row, bold=(i == 0))
pdf.ln(3)
pdf.body(
    "Rates shown are for well-qualified borrowers and are subject to credit approval, income "
    "verification, and property appraisal (where applicable). Final rate depends on credit score, "
    "loan-to-value ratio, debt-to-income ratio, and relationship pricing discounts."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 4 - Overdraft Protection
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(4, "Overdraft Protection Policy")

pdf.body(
    "Enso National Bank provides three overdraft protection options to help customers "
    "avoid declined transactions and returned items:"
)

pdf.sub_title("4.1 Overdraft Transfer Service")
pdf.body(
    "Links a checking account to a savings, money market, or credit card account. When the "
    "checking balance is insufficient, funds are automatically transferred in $100 increments "
    "to cover the shortfall. A $12 transfer fee applies per transfer day (not per item). "
    "Enrollment is free and can be set up online, at a branch, or by phone."
)

pdf.sub_title("4.2 Overdraft Line of Credit")
pdf.body(
    "An unsecured revolving line of credit ($500 - $5,000) linked to the checking account. "
    "When the checking balance goes negative, funds are advanced from the line of credit. "
    "Interest accrues at 18.00% APR (variable, tied to Prime Rate + 9.50%). No per-transfer "
    "fee applies. Minimum monthly payment of $25 or 2% of the outstanding balance, whichever "
    "is greater. Subject to credit approval."
)

pdf.sub_title("4.3 Standard Overdraft Coverage (Courtesy Pay)")
pdf.body(
    "At the bank's discretion, we may authorize and pay overdrafts on checks and ACH "
    "transactions up to a -$500 limit. A $35 overdraft fee applies per item (maximum 3 fees "
    "per business day). A $5 de minimis threshold applies -- transactions that would overdraw "
    "the account by $5 or less will not incur a fee. Customers have the right to opt out of "
    "courtesy pay at any time.\n\n"
    "For ATM and one-time debit card transactions, overdraft coverage is NOT automatically "
    "provided. Customers must affirmatively opt in per Regulation E to allow these transactions "
    "to be authorized when the account has insufficient funds."
)

pdf.sub_title("4.4 Overdraft Fee Caps and Relief")
pdf.body(
    "Effective January 2025, Enso National Bank has implemented the following consumer-friendly measures:\n"
    "- Maximum of 3 overdraft fees per business day (down from 5 previously)\n"
    "- No overdraft fee on transactions of $5.00 or less\n"
    "- Grace period: If the account is brought to a positive balance by 11:59 PM ET on the next "
    "business day, the overdraft fee will be reversed automatically\n"
    "- Customers who overdraft more than 6 times in a rolling 12-month period will be contacted "
    "by a financial counselor to discuss alternative products and budgeting resources"
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 5 - Card Policies
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(5, "Debit and Credit Card Policies")

pdf.sub_title("5.1 Debit Card")
pdf.body(
    "Every checking account includes a Visa or Mastercard branded debit card. Daily transaction "
    "limits:\n"
    "- POS purchases: $5,000 per day\n"
    "- ATM withdrawals: $500 per day (can be temporarily raised to $1,000 via mobile app)\n"
    "- Online/phone purchases: $3,000 per day\n\n"
    "Customers may freeze/unfreeze their debit card instantly through the Enso mobile app. "
    "Lost or stolen cards should be reported immediately by calling 1-800-ENSO-BANK or through "
    "the mobile app. Provisional credit for disputed transactions is typically issued within "
    "10 business days per Regulation E."
)

pdf.sub_title("5.2 Credit Card Products")
pdf.body(
    "Enso National Bank offers three credit card products:\n\n"
    "Enso Everyday Card: No annual fee, 1% cash back on all purchases, 15.99%-23.99% APR.\n\n"
    "Enso Rewards Plus: $95 annual fee, 2X points on dining and travel, 1X on everything else, "
    "50,000 bonus points after $3,000 spend in first 90 days, 17.99%-25.99% APR.\n\n"
    "Enso Platinum Elite: $250 annual fee, 3X points on travel, 2X on dining, 1X other, "
    "Priority Pass lounge access, Global Entry/TSA Pre credit ($100), travel insurance, "
    "19.99%-27.99% APR."
)

pdf.sub_title("5.3 Credit Card Payment Policy")
pdf.body(
    "Minimum payment due is the greater of: (a) $25, or (b) 1% of the statement balance plus "
    "interest and fees. Payment due date is 25 days after the statement closing date. Payments "
    "received after 5:00 PM ET are posted the next business day.\n\n"
    "Late payment fee: $29 for the first occurrence in the prior 6 billing cycles; $40 for "
    "subsequent occurrences. Two consecutive missed payments may result in a penalty APR of "
    "29.99%, which will be reviewed after 6 consecutive on-time payments."
)

pdf.sub_title("5.4 Rewards Program")
pdf.body(
    "Points earned on Enso credit cards can be redeemed for:\n"
    "- Statement credits (1 point = $0.01)\n"
    "- Travel bookings through the Enso Travel portal (1 point = $0.0125)\n"
    "- Gift cards from 100+ retailers\n"
    "- Merchandise from the rewards catalog\n"
    "- Charitable donations\n\n"
    "Points expire 36 months after the billing cycle in which they were earned, unless the "
    "account is in good standing with activity in the trailing 12 months. Points are forfeited "
    "upon account closure or charge-off."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 6 - Loan Policies
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(6, "Loan Policies")

pdf.sub_title("6.1 Eligibility and Underwriting")
pdf.body(
    "All loan applications are evaluated based on the following criteria:\n"
    "- Credit score (minimum 620 for most products; 580 for FHA-eligible mortgages)\n"
    "- Debt-to-income ratio (maximum 43% for qualified mortgages per CFPB ATR/QM rule)\n"
    "- Employment verification (2 years of stable employment history preferred)\n"
    "- Income documentation (pay stubs, W-2s, tax returns for previous 2 years)\n"
    "- Collateral appraisal (for secured loans)\n\n"
    "Relationship Discount: Customers who maintain a combined deposit balance of $25,000+ "
    "across Enso accounts receive a 0.25% APR reduction on new loans."
)

pdf.sub_title("6.2 Mortgage Specific Policies")
pdf.body(
    "Loan-to-Value (LTV) Requirements:\n"
    "- Conventional: Up to 97% LTV with PMI; 80% LTV to waive PMI\n"
    "- Jumbo (> $726,200): Maximum 80% LTV, 720+ credit score required\n"
    "- Home Equity / HELOC: Maximum 85% Combined LTV\n\n"
    "Escrow: Property tax and homeowner's insurance escrow is required for loans with LTV > 80%. "
    "Escrow analysis is performed annually; surplus exceeding $50 is refunded to the borrower.\n\n"
    "PMI Cancellation: Borrowers may request PMI cancellation when LTV reaches 80% based on "
    "original property value. PMI is automatically terminated at 78% LTV per the Homeowners "
    "Protection Act."
)

pdf.sub_title("6.3 Late Payment and Default")
pdf.body(
    "Loan payments are due on the date specified in the promissory note. A 15-day grace period "
    "applies to mortgage loans; 10-day grace period for other loan types.\n\n"
    "Late fees:\n"
    "- Mortgage: 5% of the past-due principal and interest payment\n"
    "- Auto: $25 or 5% of the payment, whichever is less\n"
    "- Personal/Student: $25 flat fee\n"
    "- HELOC: $25 flat fee\n\n"
    "Loans 30+ days past due are reported to all three credit bureaus (Equifax, Experian, "
    "TransUnion). Loans 90+ days past due may be referred to collections. Foreclosure "
    "proceedings may commence after 120 days of delinquency per CFPB mortgage servicing rules."
)

pdf.sub_title("6.4 Prepayment")
pdf.body(
    "All consumer loans may be prepaid in full or in part without penalty, except:\n"
    "- Jumbo mortgages originated before January 2025 may carry a 2% prepayment penalty "
    "in the first 3 years\n"
    "- HELOCs closed within 36 months of origination incur a $350 early termination fee\n\n"
    "Extra principal payments can be made at any time and will be applied after current interest "
    "is satisfied. Customers may specify application of extra payments to principal via written "
    "instruction or through online banking."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 7 - Fraud & Security
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(7, "Fraud Prevention and Security")

pdf.sub_title("7.1 Fraud Monitoring")
pdf.body(
    "Enso National Bank employs real-time fraud detection systems that monitor all card "
    "transactions, ACH activity, wire transfers, and online banking sessions. Alerts are "
    "generated for:\n"
    "- Transactions in geographic locations inconsistent with the customer's profile\n"
    "- Rapid succession of card-not-present transactions\n"
    "- Large wire transfers to new recipients\n"
    "- Login attempts from unrecognized devices or IP addresses\n"
    "- ATM withdrawals exceeding daily limits or in unusual locations\n\n"
    "When fraud is suspected, the bank may temporarily restrict the account and contact the "
    "customer via phone, SMS, or push notification to verify the transaction."
)

pdf.sub_title("7.2 Customer Liability for Unauthorized Transactions")
pdf.body(
    "Debit Card (Regulation E):\n"
    "- Reported within 2 business days: Maximum $50 liability\n"
    "- Reported after 2 but within 60 days: Maximum $500 liability\n"
    "- Reported after 60 days: Potentially unlimited liability\n\n"
    "Credit Card (Regulation Z / TILA):\n"
    "- Maximum $50 liability for unauthorized use if reported promptly\n"
    "- Enso Zero Liability Policy: We waive all liability for unauthorized credit card "
    "transactions reported within 30 days of the statement date, regardless of amount.\n\n"
    "Customers must review statements promptly and report discrepancies within 60 days."
)

pdf.sub_title("7.3 Identity Theft Response")
pdf.body(
    "Customers who believe they are victims of identity theft should:\n"
    "1. Contact Enso immediately at 1-800-ENSO-BANK (24/7 fraud hotline)\n"
    "2. Place a fraud alert or credit freeze with the three credit bureaus\n"
    "3. File a report with the FTC at IdentityTheft.gov\n"
    "4. File a police report (optional but recommended)\n\n"
    "Enso will conduct a thorough investigation, issue new account numbers and cards, "
    "and provide complimentary credit monitoring for 12 months through our partnership "
    "with TransUnion."
)

pdf.sub_title("7.4 Online Banking Security")
pdf.body(
    "Security measures for Enso Online and Mobile Banking:\n"
    "- Multi-factor authentication (MFA) required for all logins\n"
    "- Biometric login (fingerprint, Face ID) supported on mobile\n"
    "- Session timeout after 10 minutes of inactivity\n"
    "- Device registration and management\n"
    "- Real-time login alerts via email and push notification\n"
    "- 256-bit TLS encryption for all data in transit\n"
    "- Tokens and sensitive data encrypted at rest using AES-256\n\n"
    "Customers are responsible for maintaining the security of their login credentials "
    "and must not share passwords, PINs, or one-time codes with anyone, including bank "
    "employees. Enso will never ask for your full password via phone, email, or text."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 8 - Digital Banking
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(8, "Digital Banking Services")

pdf.sub_title("8.1 Online Banking")
pdf.body(
    "Enso Online Banking provides 24/7 access to:\n"
    "- Account balances and transaction history (up to 7 years)\n"
    "- Bill pay (one-time and recurring; free for all accounts)\n"
    "- Internal and external fund transfers (ACH: free; same-day ACH: $5)\n"
    "- Wire transfers (see fee schedule)\n"
    "- eStatements and tax documents (1099-INT, 1098)\n"
    "- Secure messaging with customer support\n"
    "- Account alerts and notifications (balance thresholds, large transactions, due dates)"
)

pdf.sub_title("8.2 Mobile Banking App")
pdf.body(
    "The Enso Mobile Banking app (iOS 15+ / Android 12+) offers all Online Banking features "
    "plus:\n"
    "- Mobile check deposit (daily limit: $10,000; monthly: $25,000)\n"
    "- Card freeze/unfreeze\n"
    "- Cardless ATM access (QR code at Enso ATMs)\n"
    "- Spending insights and budgeting tools\n"
    "- Branch and ATM locator with appointment scheduling\n"
    "- Zelle(R) peer-to-peer payments (daily limit: $2,500; weekly: $10,000)"
)

pdf.sub_title("8.3 Zelle(R) Transfer Policy")
pdf.body(
    "Zelle transfers are irrevocable once submitted. Enso National Bank cannot recall or "
    "reverse completed Zelle payments. Customers should only send money to people they know "
    "and trust. Enso is not liable for payments sent to the wrong recipient due to customer "
    "error. Daily send limit: $2,500. Daily receive limit: unlimited. New enrollees may have "
    "reduced limits ($500/day) for the first 30 days."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 9 - Regulatory Compliance
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(9, "Regulatory Compliance")

pdf.sub_title("9.1 Bank Secrecy Act / Anti-Money Laundering (BSA/AML)")
pdf.body(
    "Enso National Bank maintains a comprehensive BSA/AML program that includes:\n"
    "- Customer Due Diligence (CDD) and Enhanced Due Diligence (EDD) for high-risk customers\n"
    "- Beneficial Ownership identification for legal entity customers (per FinCEN CDD Rule)\n"
    "- Suspicious Activity Report (SAR) filing when warranted\n"
    "- Currency Transaction Report (CTR) filing for cash transactions exceeding $10,000\n"
    "- Ongoing transaction monitoring using automated systems\n"
    "- OFAC screening of all customers and transactions against the SDN list\n\n"
    "Customers may not structure transactions to avoid reporting thresholds. Structuring is "
    "a federal crime under 31 U.S.C. § 5324."
)

pdf.sub_title("9.2 Privacy Policy (Gramm-Leach-Bliley Act)")
pdf.body(
    "Enso National Bank collects and protects nonpublic personal information (NPI) in "
    "accordance with the Gramm-Leach-Bliley Act (GLBA) and Regulation P.\n\n"
    "Information collected: name, address, SSN, income, account balances, transaction history, "
    "credit history, and payment records.\n\n"
    "Information sharing: We may share NPI with:\n"
    "- Service providers who perform functions on our behalf (under contractual confidentiality)\n"
    "- Credit bureaus (account status, payment history)\n"
    "- As required by law (subpoenas, regulatory examinations)\n\n"
    "We do NOT sell customer information to third parties for marketing purposes. "
    "Customers may opt out of marketing communications at any time via online banking "
    "settings, by calling 1-800-ENSO-BANK, or by mailing the opt-out form."
)

pdf.sub_title("9.3 FDIC Insurance")
pdf.body(
    "All deposit accounts at Enso National Bank are insured by the Federal Deposit Insurance "
    "Corporation (FDIC) up to $250,000 per depositor, per ownership category. Coverage "
    "categories include:\n"
    "- Single accounts\n"
    "- Joint accounts ($250,000 per co-owner)\n"
    "- Revocable trust accounts ($250,000 per beneficiary, up to 5)\n"
    "- IRAs and other retirement accounts\n\n"
    "Customers with deposits approaching FDIC limits should consult with a banker about "
    "ownership restructuring or our IntraFi(R) Network Deposits (IND) program, which provides "
    "extended FDIC coverage across a network of participating banks."
)

pdf.sub_title("9.4 Fair Lending")
pdf.body(
    "Enso National Bank is committed to fair and equitable lending practices in compliance "
    "with the Equal Credit Opportunity Act (ECOA), Fair Housing Act, and Community "
    "Reinvestment Act (CRA). We do not discriminate on the basis of race, color, religion, "
    "national origin, sex, marital status, age, receipt of public assistance, or exercise of "
    "rights under the Consumer Credit Protection Act.\n\n"
    "Loan applications are evaluated based on creditworthiness criteria applied consistently "
    "to all applicants. Adverse action notices are provided in accordance with ECOA and the "
    "Fair Credit Reporting Act (FCRA)."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 10 - Customer Support & Dispute Resolution
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(10, "Customer Support and Dispute Resolution")

pdf.sub_title("10.1 Contact Channels")
pdf.body(
    "Enso National Bank offers multiple support channels:\n"
    "- Phone: 1-800-ENSO-BANK (Mon-Fri 7 AM - 10 PM ET; Sat 8 AM - 5 PM ET)\n"
    "- 24/7 Fraud Hotline: 1-800-ENSO-FRAUD\n"
    "- Online Chat: Available via ensobank.com and the mobile app (Mon-Fri 8 AM - 8 PM ET)\n"
    "- Email: support@ensobank.com (response within 1 business day)\n"
    "- Branch: Visit any of our 10 locations during business hours\n"
    "- Secure Message: Through Online Banking (response within 24 hours)\n"
    "- Mail: Enso National Bank, P.O. Box 12345, Atlanta, GA 30301"
)

pdf.sub_title("10.2 Transaction Dispute Process")
pdf.body(
    "Debit Card Disputes (Regulation E):\n"
    "1. Customer notifies the bank of the unauthorized or erroneous transaction\n"
    "2. Bank provides provisional credit within 10 business days (20 days for new accounts)\n"
    "3. Investigation completed within 45 calendar days (90 days for POS, international, "
    "or new-account transactions)\n"
    "4. Customer notified in writing of investigation results\n"
    "5. If the dispute is denied, provisional credit is reversed with 5 business days' notice\n\n"
    "Credit Card Disputes (Regulation Z):\n"
    "1. Customer submits written dispute within 60 days of the statement date\n"
    "2. Bank acknowledges within 30 days\n"
    "3. Investigation completed within 2 billing cycles (max 90 days)\n"
    "4. Disputed amount cannot be reported as delinquent during investigation"
)

pdf.sub_title("10.3 Complaint Escalation")
pdf.body(
    "If a customer is unsatisfied with the resolution provided by frontline support:\n"
    "1. Request escalation to a team supervisor\n"
    "2. Contact the Customer Advocacy team at advocacy@ensobank.com\n"
    "3. File a regulatory complaint with:\n"
    "   - Consumer Financial Protection Bureau (CFPB): consumerfinance.gov/complaint\n"
    "   - Office of the Comptroller of the Currency (OCC): helpwithmybank.gov\n"
    "   - FDIC Consumer Assistance: fdic.gov/consumers\n\n"
    "Enso National Bank takes all complaints seriously and strives to resolve issues within "
    "5 business days. Complex matters may require up to 15 business days."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 11 - Wire Transfer Policy
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(11, "Wire Transfer Policy")

pdf.body(
    "Wire transfers are processed through the Federal Reserve's Fedwire system (domestic) "
    "and SWIFT network (international).\n"
)

pdf.sub_title("11.1 Domestic Wire Transfers")
pdf.body(
    "- Outgoing: $25 fee; available same business day if submitted before 4:00 PM ET\n"
    "- Incoming: $15 fee; typically credited within 2 hours of receipt\n"
    "- Daily limit: $50,000 (online); $250,000 (branch with manager approval)\n"
    "- Required information: recipient name, bank name, routing number, account number, "
    "amount, and purpose of transfer\n"
    "- Repetitive wire templates can be saved in online banking for recurring transfers"
)

pdf.sub_title("11.2 International Wire Transfers")
pdf.body(
    "- Outgoing: $45 fee; processing time 1-3 business days depending on destination\n"
    "- Incoming: $15 fee\n"
    "- Exchange rate: Mid-market rate plus 1.5% spread for currency conversion\n"
    "- OFAC screening applies to all international wires\n"
    "- Additional documentation may be required for transfers exceeding $10,000 or to "
    "high-risk jurisdictions per FinCEN Travel Rule requirements"
)

pdf.sub_title("11.3 Wire Transfer Fraud Prevention")
pdf.body(
    "Wire transfers are generally irrevocable. Customers should:\n"
    "- Verify recipient information through a trusted, independent channel before initiating "
    "wires, especially for real estate closings or vendor payments\n"
    "- Be wary of email-based wire instructions (Business Email Compromise is a leading "
    "source of fraud)\n"
    "- Report suspicious wire requests immediately\n\n"
    "Enso's wire transfer team performs callback verification for all first-time or modified "
    "wire recipients when the amount exceeds $10,000."
)

# ══════════════════════════════════════════════════════════════════════
# SECTION 12 - Safe Deposit Box
# ══════════════════════════════════════════════════════════════════════
pdf.section_title(12, "Safe Deposit Box Policy")

pdf.body(
    "Safe deposit boxes are available at select branch locations. Annual rental fees:\n"
    "- Small (3\"×5\"): $50/year\n"
    "- Medium (5\"×10\"): $100/year\n"
    "- Large (10\"×10\"): $175/year\n\n"
    "Contents are not FDIC-insured and are not covered by the bank's insurance. "
    "Customers are advised to maintain their own insurance for valuables stored in safe "
    "deposit boxes. Access requires presentation of a valid key and photo ID. Drilling "
    "fee for lost key: $150. Boxes not paid for 12+ months may be drilled and contents "
    "escheated to the state per applicable unclaimed property law."
)

# ══════════════════════════════════════════════════════════════════════
# Final page - glossary/definitions
# ══════════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_title(13, "Glossary of Key Terms")

terms = [
    ("APR", "Annual Percentage Rate -- the annual cost of borrowing, including interest and certain fees."),
    ("APY", "Annual Percentage Yield -- the effective annual rate of return on a deposit, accounting for compounding."),
    ("ACH", "Automated Clearing House -- an electronic network for financial transactions (direct deposits, bill payments)."),
    ("CDD", "Customer Due Diligence -- procedures for verifying the identity and assessing the risk of a customer."),
    ("CIP", "Customer Identification Program -- required identity verification under the USA PATRIOT Act."),
    ("CTR", "Currency Transaction Report -- required filing for cash transactions over $10,000."),
    ("FDIC", "Federal Deposit Insurance Corporation -- insures bank deposits up to $250,000 per depositor per ownership category."),
    ("LTV", "Loan-to-Value ratio -- the loan amount divided by the appraised property value."),
    ("MFA", "Multi-Factor Authentication -- requiring two or more verification methods (password + SMS code, etc.)."),
    ("NSF", "Non-Sufficient Funds -- when an account lacks the balance to cover a transaction."),
    ("OFAC", "Office of Foreign Assets Control -- administers trade/financial sanctions against targeted countries and individuals."),
    ("PMI", "Private Mortgage Insurance -- required when the mortgage LTV exceeds 80%."),
    ("SAR", "Suspicious Activity Report -- filed with FinCEN when suspicious banking activity is detected."),
    ("SWIFT", "Society for Worldwide Interbank Financial Telecommunication -- network for international wire transfers."),
]
for term, defn in terms:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*PolicyPDF.DARK)
    pdf.cell(18, 6, term)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*PolicyPDF.GRAY)
    pdf.multi_cell(0, 6, f"-- {defn}")
    pdf.ln(1)

# ── Save ──────────────────────────────────────────────────────────────
pdf.output(str(PDF_PATH))
print(f"PDF created: {PDF_PATH}  ({PDF_PATH.stat().st_size / 1024:.1f} KB, {pdf.pages_count} pages)")
