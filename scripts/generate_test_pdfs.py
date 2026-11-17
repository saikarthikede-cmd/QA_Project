"""Generate 6 test PDFs for manual QA testing of all 6 apps."""
from fpdf import FPDF
import os

OUT = "C:/Users/FL_LPT-592/Desktop/qa-suite/test_pdfs"
os.makedirs(OUT, exist_ok=True)


def new_pdf():
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    return pdf


def w(pdf):
    return pdf.w - pdf.l_margin - pdf.r_margin


def h1(pdf, text):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.multi_cell(w(pdf), 10, text, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_text_color(0, 0, 0)


def h2(pdf, text):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(14, 116, 144)
    pdf.multi_cell(w(pdf), 7, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)


def body(pdf, text):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(w(pdf), 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def bullet(pdf, items):
    pdf.set_font("Helvetica", "", 10)
    for item in items:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w(pdf), 6, "  - " + item, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


# -------------------------------------------------------
# PDF 1 - TechNova Employee Handbook (App 1: Strict Q&A)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "TechNova Inc. - Employee Handbook 2024")
body(pdf, "This handbook describes the policies, benefits, and expectations for all TechNova employees. Effective from January 1, 2024.")

h2(pdf, "1. Working Hours and Remote Policy")
body(pdf, "Standard working hours are 9:00 AM to 6:00 PM, Monday through Friday. Employees are entitled to a one-hour unpaid lunch break daily. TechNova operates a hybrid model: employees must be in the office a minimum of 3 days per week. Tuesday, Wednesday, and Thursday are mandatory in-office days. Fully remote arrangements require written approval from the department head and HR.")

h2(pdf, "2. Leave Entitlement")
bullet(pdf, [
    "Annual leave: 25 days per calendar year (prorated for mid-year joiners).",
    "Sick leave: 12 days per year, no carry-forward.",
    "Parental leave: 26 weeks fully paid for primary caregiver; 4 weeks for secondary caregiver.",
    "Bereavement leave: 5 days for immediate family, 2 days for extended family.",
    "Public holidays: 14 days in 2024 as per the national calendar.",
])

h2(pdf, "3. Compensation and Payroll")
body(pdf, "Salaries are paid on the last working day of each month via direct bank transfer. Annual salary reviews are conducted every April. Performance bonuses are awarded in December based on individual KPI scores and company profitability. The target bonus for mid-level employees is 10 to 15 percent of annual salary.")

h2(pdf, "4. Health and Insurance Benefits")
bullet(pdf, [
    "Medical insurance: Covers employee, spouse, and up to 2 children. Premium fully paid by TechNova.",
    "Dental: Annual limit of $1,500 per employee.",
    "Vision: Annual limit of $500 per employee.",
    "Life insurance: 3x annual salary coverage.",
    "Gym membership: $75 per month reimbursement upon submission of receipts.",
])

pdf.add_page()
h1(pdf, "TechNova Inc. - Employee Handbook 2024 (continued)")

h2(pdf, "5. Code of Conduct")
body(pdf, "All employees must act with integrity, respect colleagues and clients, and maintain confidentiality of company information. Harassment, discrimination, and conflicts of interest must be reported to HR immediately. Violations may result in disciplinary action up to and including termination.")

h2(pdf, "6. IT and Equipment Policy")
body(pdf, "Each employee receives a company laptop (MacBook Pro 14 inch or equivalent) and a $500 home office setup allowance. Company devices must not be used for personal business. All data must be stored in company-approved cloud storage (Google Drive or Confluence). VPN must be used when accessing internal systems remotely.")
bullet(pdf, [
    "Software must be approved by IT before installation.",
    "Passwords must be at least 16 characters and rotated every 90 days.",
    "Lost or stolen devices must be reported to IT within 2 hours.",
])

h2(pdf, "7. Performance Management")
body(pdf, "TechNova uses a bi-annual review cycle: mid-year check-in in July and full review in December. Employees are rated on a 5-point scale: 1 = Below Expectations, 2 = Developing, 3 = Meeting Expectations, 4 = Exceeding Expectations, 5 = Outstanding. Two consecutive ratings of 1 trigger a Performance Improvement Plan (PIP). Employees rated 4 or 5 are eligible for fast-track promotion.")

h2(pdf, "8. Termination and Notice Period")
bullet(pdf, [
    "Probation period: 3 months. Either party may terminate with 1 week notice during probation.",
    "Post-probation: Minimum 1 month notice required by either party.",
    "Senior roles (Director and above): 3 months notice period.",
    "Garden leave may be applied at company discretion during notice period.",
    "Final salary and accrued leave paid within 14 days of last working day.",
])

h2(pdf, "9. Expense Reimbursement")
body(pdf, "Business expenses must be submitted within 30 days of the expense date via the Expensify system. Receipts are mandatory for all claims above $25. Approved categories include travel, client entertainment (limit $100 per person per meal), training materials, and conference fees. Expenses exceeding $500 require pre-approval from a manager.")

h2(pdf, "10. Grievance Procedure")
body(pdf, "Employees with a grievance should first raise it informally with their line manager. If unresolved within 5 working days, a formal written grievance can be submitted to HR. HR will investigate and respond within 15 working days. Employees may appeal decisions to the CEO within 10 days of receiving HR's response.")

pdf.output(f"{OUT}/app1_employee_handbook.pdf")
print("OK PDF 1: app1_employee_handbook.pdf")


# -------------------------------------------------------
# PDF 2a - ShopEasy Policy Version A (App 2: Multi-Doc)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "ShopEasy - Customer Policy Guide (Version A - 2023)")
body(pdf, "This document outlines ShopEasy's official policies for returns, shipping, and customer support as of January 2023.")

h2(pdf, "1. Return Policy")
body(pdf, "Customers may return any item within 30 days of the original purchase date. Items must be unused, in original packaging, and accompanied by the original receipt. Refunds are issued to the original payment method within 5 to 7 business days of receiving the returned item. Sale items are non-refundable.")

h2(pdf, "2. Shipping Policy")
body(pdf, "Standard shipping takes 5 to 7 business days and costs $4.99 for orders under $50. Orders above $50 qualify for free standard shipping. Express shipping (2 to 3 business days) costs $12.99. Same-day delivery is available in select metro areas for $19.99.")

h2(pdf, "3. Damaged or Defective Items")
body(pdf, "If an item arrives damaged or defective, customers must notify ShopEasy within 48 hours of delivery via email to support@shopeasy.com with photos attached. A full refund or replacement will be arranged at no cost to the customer. Shipping costs for defective returns are covered by ShopEasy.")

h2(pdf, "4. Warranty")
body(pdf, "All electronics carry a 12-month manufacturer warranty. ShopEasy offers an extended warranty plan (ShopEasy Plus) for $9.99 per month covering accidental damage and theft for up to 24 months.")

h2(pdf, "5. Customer Support Hours")
body(pdf, "Support is available Monday to Friday, 9 AM to 5 PM EST. Average response time is 24 hours for emails and under 10 minutes for live chat.")

h2(pdf, "6. Loyalty Programme")
body(pdf, "ShopEasy Rewards members earn 1 point per $1 spent. Points can be redeemed at a rate of 100 points = $1 discount. Points expire after 12 months of account inactivity. Gold status (500 or more points per year) grants free express shipping on all orders.")

pdf.output(f"{OUT}/app2_policy_version_A.pdf")
print("OK PDF 2a: app2_policy_version_A.pdf")


# -------------------------------------------------------
# PDF 2b - ShopEasy Policy Version B (contradicts A)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "ShopEasy - Customer Policy Guide (Version B - 2024 Update)")
body(pdf, "This document outlines ShopEasy's UPDATED policies effective January 2024. This version supersedes all previous policy documents.")

h2(pdf, "1. Return Policy")
body(pdf, "Customers may return any item within 60 days of the original purchase date (UPDATED from 30 days). Items must be in resalable condition; original packaging is preferred but not required. Proof of purchase (receipt or order confirmation email) is required. Refunds are processed within 10 business days. UPDATED: Sale items are now eligible for store credit refunds only.")

h2(pdf, "2. Shipping Policy")
body(pdf, "Standard shipping now takes 3 to 5 business days (improved from 5 to 7 days) and is FREE for all orders above $35 (reduced from $50 threshold). Express shipping costs $9.99 (reduced from $12.99). Same-day delivery has been discontinued in all regions as of March 2024.")

h2(pdf, "3. Damaged or Defective Items")
body(pdf, "Customers now have 7 days (previously 48 hours) to report damaged or defective items. Reports can be made via the ShopEasy app, email, or phone. Photo evidence is required only for items valued above $100.")

h2(pdf, "4. Warranty")
body(pdf, "Electronics now carry an 18-month manufacturer warranty (extended from 12 months). The ShopEasy Plus extended warranty plan has been discontinued and is no longer available for new subscriptions.")

h2(pdf, "5. Customer Support Hours")
body(pdf, "Support is now available 7 days a week, 8 AM to 9 PM EST. Average response time is 4 hours for emails and under 2 minutes for live chat (significantly improved).")

h2(pdf, "6. Loyalty Programme")
body(pdf, "ShopEasy Rewards now earns 2 points per $1 spent (doubled from 1 point). Redemption rate unchanged: 100 points = $1 discount. Points now expire after 24 months of inactivity (extended from 12 months). Gold status threshold raised to 1,000 points per year (up from 500).")

pdf.output(f"{OUT}/app2_policy_version_B.pdf")
print("OK PDF 2b: app2_policy_version_B.pdf")


# -------------------------------------------------------
# PDF 3 - Space Exploration Report (App 3: Conv. RAG)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "The Future of Space Exploration - A 2024 Overview")
body(pdf, "This report examines the current state of human and robotic space exploration, key missions planned for 2025 to 2030, and the emerging role of private companies in the space industry.")

h2(pdf, "1. Overview of Current Space Programmes")
body(pdf, "As of 2024, three major space agencies dominate human spaceflight: NASA (USA), ESA (Europe), and Roscosmos (Russia), with CNSA (China) rapidly expanding its capabilities. The International Space Station (ISS) continues to serve as humanity's primary platform for microgravity research, hosting rotating crews of 6 to 7 astronauts. The ISS is planned for deorbit by 2030.")

h2(pdf, "2. The Artemis Programme")
body(pdf, "NASA's Artemis programme aims to return humans to the Moon by 2026, with the first crewed lunar landing since Apollo 17 in 1972. Artemis III will land astronauts near the lunar south pole to search for water ice. The Space Launch System (SLS) rocket stands 98 metres tall and is the most powerful ever launched. The mission will use SpaceX's Starship as the Human Landing System.")

h2(pdf, "3. Mars Exploration")
body(pdf, "NASA's Perseverance rover continues to collect rock samples on Mars, targeting sites believed to have held ancient microbial life. A joint NASA-ESA Mars Sample Return mission is planned for the early 2030s. China's Tianwen-1 mission successfully deployed the Zhurong rover in 2021. SpaceX's Starship is targeted for an uncrewed Mars mission as early as 2026, with crewed missions eyed for the late 2020s.")

h2(pdf, "4. Private Space Companies")
body(pdf, "SpaceX, founded by Elon Musk, has become the world's largest launch provider with Falcon 9 rockets completing over 250 successful missions. Blue Origin (Jeff Bezos) is developing the New Glenn orbital rocket and the Blue Moon lunar lander. Virgin Galactic offers suborbital tourist flights at $450,000 per seat. Rocket Lab focuses on small satellite launch services with its Electron rocket.")

pdf.add_page()
h1(pdf, "The Future of Space Exploration (continued)")

h2(pdf, "5. Commercial Space Stations")
body(pdf, "With the ISS nearing end-of-life, NASA has contracted three private companies to build commercial space stations: Axiom Space (Axiom Station), Blue Origin (Orbital Reef), and Nanoracks (Starlab). These are expected to be operational between 2028 and 2032 and will host both government astronauts and private visitors.")

h2(pdf, "6. Space Tourism")
body(pdf, "The space tourism market is projected to reach $8 billion by 2030. SpaceX's Inspiration4 mission in 2021 was the first all-civilian orbital spaceflight. Axiom Space has sold private ISS missions at approximately $55 million per seat. Orbital tourism remains limited by high costs, while suborbital flights from Blue Origin and Virgin Galactic offer a more accessible entry point.")

h2(pdf, "7. The Starship Spacecraft")
body(pdf, "SpaceX's Starship is a fully reusable stainless-steel spacecraft standing 120 metres tall when combined with its Super Heavy booster. It uses 33 Raptor engines burning liquid methane. Starship is designed to carry up to 100 passengers and is central to SpaceX's ambition of colonising Mars. It conducted its first successful integrated test flight in 2024.")

h2(pdf, "8. Key Challenges")
bullet(pdf, [
    "Radiation exposure: Astronauts on lunar or Mars missions face radiation 300x higher than on Earth.",
    "Bone and muscle loss: Microgravity causes 1 to 2 percent bone density loss per month.",
    "Communication delay: Mars signals take 3 to 22 minutes one-way, making real-time control impossible.",
    "Funding: NASA's annual budget is approximately $25 billion, less than 0.5% of US federal spending.",
    "Space debris: Over 27,000 pieces of tracked orbital debris pose collision risks.",
])

h2(pdf, "9. Notable Upcoming Missions (2025 to 2030)")
bullet(pdf, [
    "2025: Artemis II - first crewed Orion flight around the Moon (no landing).",
    "2026: Artemis III - first crewed lunar landing since 1972, near south pole.",
    "2026: SpaceX uncrewed Starship to Mars.",
    "2027: ESA JUICE spacecraft arrives at Jupiter system.",
    "2028: First commercial space station modules launched.",
    "2030: ISS deorbit. NASA aims for sustained lunar presence via Gateway station.",
])

h2(pdf, "10. Conclusion")
body(pdf, "The next decade will likely see more human activity in space than any previous era. The convergence of government ambition and private investment is accelerating timelines. Whether humanity establishes a permanent lunar base or sends the first crew to Mars within the decade remains uncertain, but the trajectory is unprecedented.")

pdf.output(f"{OUT}/app3_space_exploration.pdf")
print("OK PDF 3: app3_space_exploration.pdf")


# -------------------------------------------------------
# PDF 4 - Nexora Annual Report (App 4: Report Summarizer)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "Nexora Financial Services - Annual Report 2023")
body(pdf, "Prepared by the Strategy and Analytics Division. Confidential - For internal use only. Fiscal year ending December 31, 2023.")

h2(pdf, "Executive Overview")
body(pdf, "2023 was a transformative year for Nexora Financial Services. Total revenue reached $142 million, a 23% increase year-over-year. Net profit grew to $31.2 million (margin: 22%). Customer base expanded from 85,000 to 114,000 active accounts, a 34% increase driven primarily by the launch of the NexoraPay mobile platform in Q2.")

h2(pdf, "Key Performance Indicators")
bullet(pdf, [
    "Total Revenue: $142 million (2022: $115 million, +23% YoY)",
    "Net Profit: $31.2 million (2022: $19.8 million, +58% YoY)",
    "Total Assets Under Management: $2.8 billion",
    "Active Customer Accounts: 114,000",
    "Customer Acquisition Cost (CAC): $187 per customer",
    "Customer Lifetime Value (CLV): $2,340",
    "Employee Headcount: 892 (2022: 731)",
    "Net Promoter Score (NPS): 67 (industry average: 42)",
])

h2(pdf, "Revenue Breakdown by Division")
bullet(pdf, [
    "Retail Banking: $58 million (41% of revenue)",
    "Wealth Management: $39 million (27% of revenue)",
    "Insurance Products: $28 million (20% of revenue)",
    "Digital / Fintech Services (NexoraPay): $17 million (12% of revenue)",
])

h2(pdf, "Key Findings")
body(pdf, "Three strategic themes defined 2023: digital acceleration, geographic expansion, and operational efficiency.")
body(pdf, "Digital Acceleration: The NexoraPay app reached 62,000 downloads within 6 months of launch and processed $890 million in transactions in its first year. Digital channels now account for 71% of all customer interactions, up from 44% in 2021.")
body(pdf, "Geographic Expansion: Nexora opened 3 new regional offices in Austin, Denver, and Miami contributing $12 million in new revenue. The Southeast US market showed the highest growth rate at 41%.")
body(pdf, "Operational Efficiency: Cost-to-income ratio improved from 68% to 61%. Automation of back-office processes saved an estimated $4.2 million annually.")

pdf.add_page()
h1(pdf, "Nexora Financial Services - Annual Report 2023 (continued)")

h2(pdf, "Risks and Challenges")
bullet(pdf, [
    "Regulatory compliance costs increased 18% due to new SEC reporting requirements.",
    "Cybersecurity incident in March 2023: 1,200 accounts temporarily frozen. No data breached. Cost: $780,000.",
    "Rising interest rates compressed mortgage lending margins by approximately 1.4%.",
    "Talent acquisition remains competitive: 34 senior roles unfilled for more than 90 days.",
    "NexoraPay faces growing competition from three well-funded fintech startups.",
])

h2(pdf, "Strategic Recommendations for 2024")
bullet(pdf, [
    "Accelerate NexoraPay international rollout - target Canada and UK by Q3 2024.",
    "Launch premium wealth management tier (Nexora Elite) for clients with $500k+ AUM.",
    "Invest $8 million in cybersecurity infrastructure upgrades across all systems.",
    "Partner with two regional credit unions to expand rural customer base.",
    "Reduce CAC by 20% through targeted digital marketing optimisation.",
    "Hire 120 additional staff focused on engineering, compliance, and customer success.",
])

h2(pdf, "Quarterly Revenue Summary")
bullet(pdf, [
    "Q1 2023: $29.4 million",
    "Q2 2023: $33.1 million (NexoraPay launched June 2023)",
    "Q3 2023: $37.8 million (strongest quarter)",
    "Q4 2023: $41.7 million (year-end investment surge)",
])

h2(pdf, "Conclusion")
body(pdf, "Nexora enters 2024 from a position of strength. The digital strategy is yielding measurable results, the balance sheet is healthy, and customer sentiment is at an all-time high. The board has approved a 2024 revenue target of $178 million with continued focus on NexoraPay growth and geographic diversification.")

pdf.output(f"{OUT}/app4_nexora_annual_report.pdf")
print("OK PDF 4: app4_nexora_annual_report.pdf")


# -------------------------------------------------------
# PDF 5 - CloudDesk Support Policy (App 5: Policy Triage)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "CloudDesk SaaS - Customer Support and Refund Policy")
body(pdf, "Version 3.2 | Effective: March 1, 2024 | Applies to all CloudDesk subscription plans.")

h2(pdf, "1. Subscription Plans and Pricing")
bullet(pdf, [
    "Starter Plan: $29/month - Up to 3 users, 10 GB storage, email support only.",
    "Professional Plan: $99/month - Up to 20 users, 100 GB storage, email and live chat support.",
    "Enterprise Plan: $399/month - Unlimited users, 1 TB storage, 24/7 phone and priority support.",
    "Annual billing: 20% discount applied. No refunds on annual plans after 30-day trial.",
])

h2(pdf, "2. Free Trial Policy")
body(pdf, "All new accounts receive a 14-day free trial with full Professional Plan features. No credit card required for the trial. At the end of the trial, accounts are automatically downgraded to a read-only state until a plan is selected. Trial extensions of up to 7 days may be granted once per account at support team discretion.")

h2(pdf, "3. Refund Policy")
body(pdf, "Monthly plans: Customers may request a full refund within 7 days of any monthly billing date. Requests made after 7 days are not eligible for a refund for that billing period. The subscription will be cancelled at the end of the current period.")
body(pdf, "Annual plans: A full refund is available within 30 days of the annual payment date. After 30 days, a prorated refund is available for unused complete months only, minus a $50 administration fee.")
body(pdf, "Non-refundable items: Setup fees, add-on purchases (extra storage, API calls), and professional services engagements are non-refundable under any circumstances.")

h2(pdf, "4. Service Level Agreement (SLA)")
bullet(pdf, [
    "Starter: Best-effort response within 2 business days. No uptime SLA.",
    "Professional: Response within 8 business hours. 99.5% monthly uptime SLA.",
    "Enterprise: Response within 1 hour (24/7). 99.9% monthly uptime SLA. Dedicated account manager.",
    "SLA credits: If uptime falls below guaranteed levels, customers receive 10% credit per 0.1% below threshold.",
])

pdf.add_page()
h1(pdf, "CloudDesk SaaS - Customer Support Policy (continued)")

h2(pdf, "5. Data and Security Incidents")
body(pdf, "In the event of a confirmed data breach affecting customer data, CloudDesk will notify affected customers within 72 hours. Customers affected by a breach are entitled to: 3 months free service credit, complimentary data export, and priority migration support if they choose to cancel. Customers must submit data breach compensation claims within 90 days of the breach notification.")

h2(pdf, "6. Account Cancellation")
bullet(pdf, [
    "Monthly plans: Cancel anytime. Access continues until end of current billing period.",
    "Annual plans: Cancel anytime. No refund after 30-day window unless due to SLA breach.",
    "Data retention: All customer data is retained for 30 days after cancellation, then permanently deleted.",
    "Reactivation: Accounts can be reactivated within the 30-day retention window with all data intact.",
])

h2(pdf, "7. Dispute Resolution and Escalation")
body(pdf, "Step 1: Contact support via ticket or live chat. Target resolution: 1 to 3 business days.")
body(pdf, "Step 2: If unresolved, escalate to Support Team Lead. Target resolution: 5 business days.")
body(pdf, "Step 3: Escalate to Customer Success Manager (Professional and Enterprise plans only).")
body(pdf, "Step 4: Final escalation to VP of Customer Experience. Binding decisions made within 10 business days.")
body(pdf, "Legal disputes are governed by the laws of the State of Delaware. Arbitration is required before litigation.")

h2(pdf, "8. Prohibited Use and Termination")
body(pdf, "CloudDesk reserves the right to immediately terminate accounts found to be sending spam, hosting illegal content, performing DDoS attacks, scraping data at scale without permission, or reselling access without authorisation. No refund is issued upon termination for policy violations.")

h2(pdf, "9. Plan Upgrades and Downgrades")
body(pdf, "Upgrades take effect immediately. The customer is charged a prorated amount for the remainder of the billing period at the new plan rate. Downgrades take effect at the start of the next billing cycle. Data exceeding the lower plan's storage limit must be reduced before the downgrade is processed, or the account will be locked.")

pdf.output(f"{OUT}/app5_clouddesk_policy.pdf")
print("OK PDF 5: app5_clouddesk_policy.pdf")


# -------------------------------------------------------
# PDF 6 - RetailMax Sales Data (App 6: Data Analyst)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "RetailMax Corp - Sales and Operations Data Report 2023")
body(pdf, "Internal analytics report prepared by the Business Intelligence team. Contains revenue, cost, headcount, and product data for fiscal year 2023.")

h2(pdf, "1. Annual Revenue Summary")
bullet(pdf, [
    "Total Revenue 2023: $8,450,000",
    "Total Revenue 2022: $6,920,000",
    "Year-over-Year Growth: 22.1%",
    "Total Cost of Goods Sold (COGS): $3,802,500",
    "Gross Profit: $4,647,500",
    "Gross Margin: 55%",
    "Operating Expenses: $2,112,500",
    "Net Profit: $2,535,000",
    "Net Profit Margin: 30%",
])

h2(pdf, "2. Quarterly Revenue Breakdown")
bullet(pdf, [
    "Q1 (Jan-Mar 2023): $1,690,000",
    "Q2 (Apr-Jun 2023): $1,972,000",
    "Q3 (Jul-Sep 2023): $2,338,500",
    "Q4 (Oct-Dec 2023): $2,449,500",
    "Best performing month: December 2023 at $1,100,000",
    "Weakest performing month: February 2023 at $480,000",
])

h2(pdf, "3. Revenue by Product Category")
bullet(pdf, [
    "Electronics: $3,380,000 (40% of revenue)",
    "Clothing and Apparel: $1,690,000 (20% of revenue)",
    "Home and Kitchen: $1,267,500 (15% of revenue)",
    "Sports and Outdoors: $1,014,000 (12% of revenue)",
    "Beauty and Personal Care: $845,000 (10% of revenue)",
    "Other: $253,500 (3% of revenue)",
])

h2(pdf, "4. Revenue by Region")
bullet(pdf, [
    "North America: $4,225,000 (50% of revenue)",
    "Europe: $2,535,000 (30% of revenue)",
    "Asia-Pacific: $1,267,500 (15% of revenue)",
    "Rest of World: $422,500 (5% of revenue)",
])

pdf.add_page()
h1(pdf, "RetailMax Corp - Sales Data Report (continued)")

h2(pdf, "5. Headcount and HR Data")
bullet(pdf, [
    "Total employees end of 2023: 214",
    "Total employees end of 2022: 178",
    "New hires in 2023: 52",
    "Voluntary turnover: 16 employees (attrition rate: 8.5%)",
    "Average salary all staff: $67,400 per year",
    "Total payroll cost 2023: $1,442,360",
    "Revenue per employee: $39,486",
])

h2(pdf, "6. Top 5 Best-Selling Products")
bullet(pdf, [
    "1. ProSound Wireless Headphones - 12,400 units - $744,000 revenue",
    "2. UltraFit Running Shoes - 9,800 units - $392,000 revenue",
    "3. SmartHome Hub v3 - 7,200 units - $576,000 revenue",
    "4. AeroBlend Pro Blender - 6,500 units - $195,000 revenue",
    "5. NovaSkin Serum Kit - 5,900 units - $413,000 revenue",
])

h2(pdf, "7. Customer Metrics")
bullet(pdf, [
    "Total unique customers 2023: 38,400",
    "Repeat purchase rate: 43%",
    "Average order value (AOV): $124",
    "Total orders placed: 68,145",
    "Return rate: 6.2% of orders",
    "Customer acquisition cost (CAC): $18.50",
    "Customer lifetime value (CLV): $312",
])

h2(pdf, "8. Marketing Spend and ROI")
bullet(pdf, [
    "Total marketing budget 2023: $620,000",
    "Digital advertising (Google and Meta): $310,000 - attributed $2,800,000 revenue",
    "Email marketing: $45,000 - attributed $980,000 revenue",
    "Influencer partnerships: $120,000 - attributed $760,000 revenue",
    "Trade shows and events: $85,000 - attributed $310,000 revenue",
    "SEO and content: $60,000 - attributed $1,200,000 revenue",
    "Overall marketing ROI: 13.6x",
])

h2(pdf, "9. Inventory and Supply Chain")
bullet(pdf, [
    "Total SKUs active: 1,842",
    "Average inventory turnover rate: 8.4x per year",
    "Stockout incidents: 23 (affecting $182,000 in potential revenue)",
    "Average lead time from suppliers: 18 days",
    "Warehouse utilisation: 78%",
    "3PL fulfilment cost per order: $6.20",
])

h2(pdf, "10. 2024 Targets")
bullet(pdf, [
    "Revenue target: $11,000,000 (30.2% growth over 2023)",
    "Net profit target: $3,300,000",
    "New customer target: 50,000",
    "Headcount target: 260 employees",
    "Launch 2 new product categories",
    "Expand to 2 new international markets",
])

pdf.output(f"{OUT}/app6_retailmax_data.pdf")
print("OK PDF 6: app6_retailmax_data.pdf")


# -------------------------------------------------------
# PDF for new App 1 - Job Description (Resume Screener)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "Job Description: Senior Backend Engineer - FinTech Platform")
body(pdf, "Company: Velox Payments | Location: Hybrid (Austin, TX) | Type: Full-time | Posted: June 2024")
body(pdf, "Velox Payments is a fast-growing B2B fintech company processing over $2 billion in transactions annually. We are looking for a Senior Backend Engineer to join our Core Platform team and help scale our payment infrastructure.")

h2(pdf, "Role Overview")
body(pdf, "You will design, build, and maintain the APIs and microservices that power Velox's payment processing engine. This is a high-impact, high-ownership role. You will collaborate closely with product, DevOps, and data engineering teams. The ideal candidate has a proven track record of building reliable, high-throughput systems in a production environment.")

h2(pdf, "Required Qualifications")
bullet(pdf, [
    "5+ years of professional software engineering experience.",
    "Expert-level Python (FastAPI, Celery, SQLAlchemy).",
    "Strong experience with PostgreSQL and Redis.",
    "Proficiency with Docker and Kubernetes in production.",
    "AWS experience: EC2, RDS, SQS, Lambda, S3.",
    "Demonstrated experience building and consuming REST APIs.",
    "Experience with message queues and event-driven architecture.",
    "Track record of leading technical projects end-to-end.",
    "Experience with CI/CD pipelines (GitHub Actions or similar).",
    "Strong understanding of security best practices in financial systems.",
])

h2(pdf, "Nice to Have")
bullet(pdf, [
    "Experience with payment gateways (Stripe, Adyen, or similar).",
    "Familiarity with PCI-DSS compliance requirements.",
    "Exposure to Go or Rust for performance-critical services.",
    "Experience with gRPC and Protocol Buffers.",
    "Prior fintech or payments domain experience.",
])

h2(pdf, "Responsibilities")
bullet(pdf, [
    "Design and build scalable microservices for payment processing.",
    "Own and improve core APIs used by 300+ enterprise clients.",
    "Conduct thorough code reviews and mentor junior engineers.",
    "Write comprehensive unit, integration, and load tests.",
    "Participate in on-call rotation (approximately 1 week per quarter).",
    "Collaborate with product managers to define technical requirements.",
    "Document system architecture and API contracts.",
])

h2(pdf, "Compensation and Benefits")
bullet(pdf, [
    "Base salary: $160,000 to $195,000 depending on experience.",
    "Equity: 0.05% to 0.15% stock options, 4-year vest with 1-year cliff.",
    "Annual performance bonus: up to 15% of base salary.",
    "Full health, dental, and vision insurance (employee + family).",
    "401k with 4% employer match.",
    "$2,000 annual learning and development budget.",
    "Home office stipend: $1,500 one-time setup + $100/month.",
    "Flexible PTO (minimum 20 days encouraged).",
])

pdf.output(f"{OUT}/app1_jd_senior_backend_engineer.pdf")
print("OK PDF: app1_jd_senior_backend_engineer.pdf")


# Resume A - Strong match
pdf = new_pdf()
pdf.add_page()
h1(pdf, "Resume: Sarah Chen")
body(pdf, "Email: sarah.chen@email.com | LinkedIn: linkedin.com/in/sarahchen | Location: Austin, TX")

h2(pdf, "Professional Summary")
body(pdf, "Senior backend engineer with 8 years of experience building high-throughput financial systems. Expert in Python microservices, cloud infrastructure, and payment processing. Led teams of 4 to 6 engineers at two high-growth fintech companies. Passionate about reliability engineering and clean API design.")

h2(pdf, "Work Experience")
body(pdf, "SENIOR SOFTWARE ENGINEER - PayCore Inc. (2020 to 2024, 4 years)")
bullet(pdf, [
    "Built and owned payment processing microservices handling 50,000 transactions/day using Python (FastAPI) and PostgreSQL.",
    "Migrated monolith to Kubernetes-based microservices on AWS, reducing latency by 40%.",
    "Designed event-driven architecture using AWS SQS and Celery for async payment workflows.",
    "Led a team of 5 engineers, conducted code reviews, and owned sprint planning.",
    "Achieved PCI-DSS Level 1 certification for the platform by implementing tokenisation and encryption.",
    "Built CI/CD pipelines using GitHub Actions with automated test coverage gates.",
])
body(pdf, "BACKEND ENGINEER - TransactIQ (2016 to 2020, 4 years)")
bullet(pdf, [
    "Developed REST APIs for a B2B payments platform using Python (Django REST Framework).",
    "Integrated with Stripe and Adyen payment gateways.",
    "Used Redis for caching and session management, reducing API response time by 35%.",
    "Managed AWS infrastructure: EC2, RDS (PostgreSQL), S3, Lambda.",
])

h2(pdf, "Technical Skills")
bullet(pdf, [
    "Languages: Python (expert), Go (intermediate), SQL",
    "Frameworks: FastAPI, Celery, SQLAlchemy, Django REST",
    "Databases: PostgreSQL, Redis, DynamoDB",
    "Cloud: AWS (EC2, RDS, SQS, Lambda, S3), certified AWS Solutions Architect",
    "DevOps: Docker, Kubernetes, GitHub Actions, Terraform",
    "Protocols: REST, gRPC, Protocol Buffers",
    "Compliance: PCI-DSS, SOC 2 Type II",
])

h2(pdf, "Education")
body(pdf, "B.S. Computer Science, University of Texas at Austin, 2016")

pdf.output(f"{OUT}/app1_resume_sarah_chen.pdf")
print("OK PDF: app1_resume_sarah_chen.pdf")


# Resume B - Partial match
pdf = new_pdf()
pdf.add_page()
h1(pdf, "Resume: Marcus Williams")
body(pdf, "Email: marcus.w@email.com | GitHub: github.com/marcusw | Location: Dallas, TX (open to hybrid)")

h2(pdf, "Summary")
body(pdf, "Backend developer with 4 years of experience in Python web development and cloud deployment. Solid foundation in REST API development and SQL databases. Looking to transition into a more infrastructure-focused senior role.")

h2(pdf, "Experience")
body(pdf, "SOFTWARE ENGINEER - Shopify Partner Agency (2021 to 2024)")
bullet(pdf, [
    "Built REST APIs using Python (Flask and Django) for e-commerce clients.",
    "Used PostgreSQL and MySQL for database design and query optimisation.",
    "Deployed applications on AWS (EC2 and S3 only) and configured basic CI/CD with CircleCI.",
    "Worked with Docker for containerisation but no Kubernetes experience.",
    "Collaborated with 2-person teams; no formal technical leadership experience.",
])
body(pdf, "JUNIOR DEVELOPER - Freelance (2020 to 2021)")
bullet(pdf, [
    "Built web applications for small businesses using Python (Django) and JavaScript.",
    "Limited cloud experience (mainly shared hosting and basic AWS EC2).",
])

h2(pdf, "Skills")
bullet(pdf, [
    "Languages: Python, JavaScript, SQL",
    "Frameworks: Django, Flask (not FastAPI)",
    "Databases: PostgreSQL, MySQL",
    "Cloud: AWS (EC2, S3 only), limited RDS experience",
    "Tools: Docker, CircleCI, Git",
    "No Kubernetes, Celery, Redis, gRPC, or payment gateway experience",
])

h2(pdf, "Education")
body(pdf, "B.S. Information Technology, University of North Texas, 2020")

pdf.output(f"{OUT}/app1_resume_marcus_williams.pdf")
print("OK PDF: app1_resume_marcus_williams.pdf")


# Resume C - Poor match
pdf = new_pdf()
pdf.add_page()
h1(pdf, "Resume: Priya Nair")
body(pdf, "Email: priya.nair@email.com | Location: Remote | Portfolio: priya-designs.com")

h2(pdf, "Professional Summary")
body(pdf, "Creative frontend developer with 6 years of experience building responsive web applications and design systems. Specialist in React, TypeScript, and CSS animation. Strong background in UX collaboration and accessibility standards.")

h2(pdf, "Experience")
body(pdf, "SENIOR FRONTEND ENGINEER - MediaFlow Studios (2019 to 2024)")
bullet(pdf, [
    "Built component libraries in React and TypeScript used across 12 product teams.",
    "Led frontend architecture for a SaaS platform with 200,000 monthly users.",
    "Collaborated with UX designers to implement WCAG 2.1 AA accessibility standards.",
    "No backend development; all work was client-side JavaScript and CSS.",
])
body(pdf, "UI DEVELOPER - AdTech Co. (2018 to 2019)")
bullet(pdf, [
    "Built advertising creative tools using React and Canvas API.",
    "Integrated with third-party REST APIs (read-only consumption, no API development).",
])

h2(pdf, "Skills")
bullet(pdf, [
    "Languages: JavaScript, TypeScript, HTML, CSS (no Python)",
    "Frameworks: React, Next.js, Storybook",
    "Tools: Figma, Webpack, Jest, Cypress",
    "No backend, cloud infrastructure, databases, or DevOps experience",
    "No Python, PostgreSQL, Docker, Kubernetes, or AWS experience",
])

h2(pdf, "Education")
body(pdf, "B.A. Graphic Design (minor: Computer Science), UCLA, 2018")

pdf.output(f"{OUT}/app1_resume_priya_nair.pdf")
print("OK PDF: app1_resume_priya_nair.pdf")


# -------------------------------------------------------
# PDFs for new App 2 - Document Diff (Terms of Service)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "Zenith Cloud Storage - Terms of Service v1.0")
body(pdf, "Effective Date: January 1, 2023 | Version 1.0 | Zenith Cloud Inc., 400 Tech Blvd, San Francisco, CA 94105")

h2(pdf, "1. Acceptance of Terms")
body(pdf, "By creating an account or using Zenith Cloud Storage services, you agree to be bound by these Terms of Service. If you do not agree, you must not use our services. These terms apply to all users including free, individual, and business accounts.")

h2(pdf, "2. Account Registration")
body(pdf, "You must provide accurate and complete registration information. You are responsible for maintaining the security of your account credentials. Accounts are limited to one per individual. Sharing account credentials with others is prohibited. You must be at least 18 years old to create an account.")

h2(pdf, "3. Data Storage and Retention")
body(pdf, "Free accounts receive 15 GB of storage. Paid plans receive storage as specified in the plan details. Zenith retains deleted files in a recoverable state for 30 days before permanent deletion. Inactive accounts (no login for 12 months) may be deleted with 30 days prior email notice.")

h2(pdf, "4. Pricing and Payment")
body(pdf, "Subscriptions are billed monthly on the anniversary of signup. Prices are listed in USD and subject to change with 30 days notice. Failed payments result in a 7-day grace period before service suspension. All sales are final; no refunds are provided for partial months.")

h2(pdf, "5. Acceptable Use")
bullet(pdf, [
    "You may not store illegal content, malware, or content that infringes third-party rights.",
    "Automated bulk uploads exceeding 1,000 files per hour are prohibited without prior approval.",
    "Reselling storage capacity to third parties is not permitted under individual plans.",
    "You may not use the service to distribute spam or phishing materials.",
])

h2(pdf, "6. Service Availability")
body(pdf, "Zenith targets 99.5% monthly uptime for paid accounts. Planned maintenance windows are communicated 48 hours in advance via email. Service credits of 10% of monthly fee are issued for downtime exceeding the SLA threshold.")

h2(pdf, "7. Termination")
body(pdf, "Either party may terminate the agreement with 30 days written notice. Zenith may immediately terminate accounts found in violation of the Acceptable Use Policy. Upon termination, you have 30 days to export your data before permanent deletion.")

h2(pdf, "8. Governing Law")
body(pdf, "These Terms are governed by the laws of the State of California. Any disputes shall be resolved in the courts of San Francisco County, California.")

pdf.output(f"{OUT}/app2_terms_v1.pdf")
print("OK PDF: app2_terms_v1.pdf")


# Terms v2 - several deliberate changes
pdf = new_pdf()
pdf.add_page()
h1(pdf, "Zenith Cloud Storage - Terms of Service v2.0")
body(pdf, "Effective Date: January 1, 2024 | Version 2.0 | UPDATED - Supersedes all prior versions | Zenith Cloud Inc., 400 Tech Blvd, San Francisco, CA 94105")

h2(pdf, "1. Acceptance of Terms")
body(pdf, "By creating an account or using Zenith Cloud Storage services, you agree to be bound by these Terms of Service. If you do not agree, you must not use our services. These terms apply to all users including free, individual, business, and enterprise accounts. UPDATED: Continued use of the service after changes constitutes acceptance of updated terms.")

h2(pdf, "2. Account Registration")
body(pdf, "You must provide accurate and complete registration information. You are responsible for maintaining the security of your account credentials. UPDATED: Accounts are now permitted up to 3 sub-accounts per paid plan for team use. Sharing account credentials with non-authorised users remains prohibited. You must be at least 16 years old to create an account (UPDATED from 18).")

h2(pdf, "3. Data Storage and Retention")
body(pdf, "Free accounts receive 5 GB of storage (REDUCED from 15 GB). Paid plans receive storage as specified in the plan details. UPDATED: Zenith retains deleted files for 90 days before permanent deletion (extended from 30 days). Inactive account deletion policy: accounts inactive for 24 months (EXTENDED from 12 months) may be deleted with 60 days prior notice.")

h2(pdf, "4. Pricing and Payment")
body(pdf, "Subscriptions are billed monthly or annually (UPDATED: annual billing now available at 15% discount). Prices are listed in USD and subject to change with 60 days notice (UPDATED from 30 days). Failed payments result in a 3-day grace period (REDUCED from 7 days) before service suspension. UPDATED: Refunds are available within 14 days of billing for monthly plans.")

h2(pdf, "5. Acceptable Use")
bullet(pdf, [
    "You may not store illegal content, malware, or content that infringes third-party rights.",
    "UPDATED: Automated bulk uploads exceeding 5,000 files per hour are prohibited (limit increased from 1,000).",
    "Reselling storage capacity to third parties is not permitted under individual or business plans.",
    "You may not use the service to distribute spam or phishing materials.",
    "ADDED: Cryptocurrency mining using Zenith infrastructure is strictly prohibited.",
])

h2(pdf, "6. Service Availability")
body(pdf, "UPDATED: Zenith now targets 99.9% monthly uptime for paid accounts (improved from 99.5%). Planned maintenance windows are communicated 72 hours in advance (UPDATED from 48 hours). Service credits of 15% of monthly fee (UPDATED from 10%) are issued for downtime exceeding the SLA threshold.")

h2(pdf, "7. Termination")
body(pdf, "Either party may terminate the agreement with 14 days written notice (REDUCED from 30 days). Zenith may immediately terminate accounts found in violation of the Acceptable Use Policy. Upon termination, you have 14 days to export your data (REDUCED from 30 days) before permanent deletion.")

h2(pdf, "8. Governing Law")
body(pdf, "UPDATED: These Terms are now governed by the laws of the State of Delaware (CHANGED from California). Any disputes shall first be submitted to binding arbitration before litigation. ADDED: Class action waiver: users waive the right to participate in class action lawsuits against Zenith.")

pdf.output(f"{OUT}/app2_terms_v2.pdf")
print("OK PDF: app2_terms_v2.pdf")


# -------------------------------------------------------
# PDF for new App 3 - SmartPay Product Manual (FAQ Gen)
# -------------------------------------------------------
pdf = new_pdf()
pdf.add_page()
h1(pdf, "SmartPay Gateway - Product Manual v4.1")
body(pdf, "SmartPay by Orbital Fintech | Support: docs.smartpay.io | Version 4.1 | Updated: April 2024")
body(pdf, "SmartPay is a cloud-based payment processing gateway that enables businesses to accept credit cards, debit cards, bank transfers, and digital wallets. This manual covers setup, features, limits, fees, security, and troubleshooting.")

h2(pdf, "1. Getting Started")
body(pdf, "To activate your SmartPay account: complete identity verification (KYC) within 7 days of signup, provide a valid business registration document, link a bank account for settlement, and configure your API keys in the developer dashboard. Accounts not verified within 7 days are suspended. Verification typically takes 1 to 3 business days.")

h2(pdf, "2. Accepted Payment Methods")
bullet(pdf, [
    "Credit cards: Visa, Mastercard, American Express, Discover.",
    "Debit cards: Visa Debit, Mastercard Debit, PIN-based debit (US only).",
    "Digital wallets: Apple Pay, Google Pay, PayPal, Shop Pay.",
    "Bank transfers: ACH (US), SEPA (Europe), BACS (UK).",
    "Buy Now Pay Later: Klarna and Afterpay available as add-ons.",
    "Cryptocurrency: Bitcoin and Ethereum via SmartPay Crypto (separate activation required).",
])

h2(pdf, "3. Transaction Limits")
bullet(pdf, [
    "Standard accounts: $10,000 per single transaction, $50,000 per day.",
    "Verified business accounts: $50,000 per single transaction, $250,000 per day.",
    "ACH transfers: $25,000 per transaction, $100,000 per day.",
    "International transactions: subject to 1.5% additional currency conversion fee.",
    "Limits can be increased with 30 days advance request and documentation.",
])

h2(pdf, "4. Fee Structure")
body(pdf, "Processing fees are charged per successful transaction. No monthly fees for standard accounts. Volume discounts apply above $50,000 per month.")
bullet(pdf, [
    "Domestic card (Visa/Mastercard): 1.9% + $0.25 per transaction.",
    "American Express: 2.4% + $0.25 per transaction.",
    "Digital wallets (Apple Pay, Google Pay): 1.9% + $0.25 (same as card).",
    "ACH bank transfer: 0.5% capped at $5.00 per transaction.",
    "International cards: additional 1.5% on top of standard rate.",
    "Chargebacks: $25 fee per dispute (refunded if you win the dispute).",
    "Refunds: no fee for refunds within 30 days. After 30 days: 0.5% processing fee.",
])

pdf.add_page()
h1(pdf, "SmartPay Gateway - Product Manual v4.1 (continued)")

h2(pdf, "5. Settlement and Payouts")
body(pdf, "Standard settlement timeline: funds are available in your linked bank account 2 business days after the transaction (T+2). Same-day payouts are available for accounts processing above $10,000/month for an additional 0.25% fee. Payouts are processed Monday through Friday excluding public holidays. Weekends and holiday transactions are batched and settled on the next business day.")

h2(pdf, "6. Refunds and Disputes")
body(pdf, "Refunds can be issued in full or partially from the SmartPay dashboard or via API. Full refunds within 30 days are processed at no fee. Partial refunds retain the original processing fee. For chargebacks: you have 7 days to submit evidence after receiving a dispute notification. Accepted evidence formats include transaction receipts, shipping confirmation, and signed agreements. SmartPay's dispute win rate for merchants with complete documentation is 68%.")

h2(pdf, "7. Security and Compliance")
body(pdf, "SmartPay is PCI-DSS Level 1 certified, the highest level of payment security compliance. All cardholder data is encrypted using AES-256. SmartPay uses 3D Secure 2.0 (3DS2) for additional authentication on high-risk transactions. Fraud detection runs on every transaction using machine learning models trained on 2 billion+ transactions.")
bullet(pdf, [
    "Two-factor authentication (2FA) is mandatory for all dashboard logins.",
    "API keys must be rotated every 90 days.",
    "Webhook endpoints must use HTTPS with a valid SSL certificate.",
    "IP whitelisting is available for API access restriction.",
])

h2(pdf, "8. Integration Options")
body(pdf, "SmartPay supports four integration methods: Hosted Checkout Page (no coding required), JavaScript Drop-in UI (embed into your site), REST API (full programmatic control), and native SDKs for iOS, Android, Python, PHP, Node.js, Ruby, and Java. All APIs use JSON and OAuth 2.0 authentication. API response time SLA: 99th percentile under 300ms.")

h2(pdf, "9. Reporting and Analytics")
body(pdf, "The SmartPay dashboard provides real-time transaction monitoring, daily/weekly/monthly revenue reports, failed payment analysis, chargeback tracking, and customer payment method breakdown. Reports can be exported as CSV or PDF. Data is retained for 7 years for compliance purposes. Custom webhooks notify your system of payment events in real-time.")

h2(pdf, "10. Support Channels")
body(pdf, "SmartPay offers multiple support channels depending on plan:")
bullet(pdf, [
    "Standard plan: Email support (response within 24 hours), documentation portal.",
    "Professional plan: Live chat (Mon-Fri 9am-6pm EST), email, documentation.",
    "Enterprise plan: 24/7 phone support, dedicated account manager, Slack connect.",
    "Developer issues: GitHub issues and Stack Overflow tag 'smartpay-api'.",
    "Emergency (service outages): status.smartpay.io and @smartpaystatus on Twitter.",
])

h2(pdf, "11. Troubleshooting Common Errors")
bullet(pdf, [
    "Error 4001 (Insufficient Funds): Card declined by issuer. Ask customer to use a different card.",
    "Error 4002 (Card Expired): Expiry date mismatch. Verify card details.",
    "Error 4003 (Do Not Honour): Generic decline. Customer must contact their bank.",
    "Error 4010 (3DS Authentication Failed): 3DS check failed. Retry or request alternate payment.",
    "Error 5001 (Gateway Timeout): SmartPay side issue. Retry after 60 seconds. If persistent, check status.smartpay.io.",
    "Error 5002 (Duplicate Transaction): Same transaction ID submitted twice. Use a unique transaction ID per attempt.",
])

pdf.output(f"{OUT}/app3_smartpay_manual.pdf")
print("OK PDF: app3_smartpay_manual.pdf")


print(f"\nAll PDFs saved to: {OUT}")
