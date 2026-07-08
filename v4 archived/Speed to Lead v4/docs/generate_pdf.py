"""Generate Phase 2 Checklist PDF using fpdf2."""
import re
from fpdf import FPDF

class ChecklistPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(107, 114, 128)
            self.cell(0, 10, 'Speed to Lead v4 - Phase 2 Client-Side Testing Checklist', 0, 0, 'L')
            self.cell(0, 10, f'Page {self.page_no()}', 0, 1, 'R')
            self.line(10, 18, 200, 18)
            self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Generated: June 8, 2026 | Speed to Lead v4 | Phase 2 Client-Side Verification', 0, 0, 'C')

    def section_title(self, text):
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(99, 102, 241)
        self.ln(4)
        self.cell(0, 10, text, 0, 1)
        # Underline
        y = self.get_y()
        self.set_draw_color(99, 102, 241)
        self.set_line_width(0.5)
        self.line(10, y, 200, y)
        self.ln(3)

    def subsection_title(self, text):
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(55, 65, 81)
        self.ln(2)
        self.cell(0, 8, text, 0, 1)
        self.ln(1)

    def body_text(self, text):
        self.set_font('Helvetica', '', 9)
        self.set_text_color(26, 26, 46)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def bold_text(self, text):
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(26, 26, 46)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def checklist_table(self, rows):
        """rows: list of (num, client_feature, technical_test, pass_fail)"""
        # Header
        self.set_font('Helvetica', 'B', 8)
        self.set_fill_color(18, 18, 26)
        self.set_text_color(232, 232, 237)
        col_widths = [8, 52, 105, 12]
        headers = ['#', 'Client Feature', 'Technical Test', 'Pass']
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, 1, 0, 'C', True)
        self.ln()

        # Rows
        self.set_font('Helvetica', '', 7.5)
        self.set_text_color(26, 26, 46)
        for idx, (num, feature, test, _) in enumerate(rows):
            # Alternate row color
            if idx % 2 == 0:
                self.set_fill_color(249, 250, 251)
            else:
                self.set_fill_color(255, 255, 255)

            # Calculate row height based on longest text
            feature_lines = self._count_lines(feature, col_widths[1] - 2)
            test_lines = self._count_lines(test, col_widths[2] - 2)
            max_lines = max(feature_lines, test_lines)
            row_h = max(max_lines * 4.2, 6)

            # Check if we need a new page
            if self.get_y() + row_h > 270:
                self.add_page()
                # Re-draw header
                self.set_font('Helvetica', 'B', 8)
                self.set_fill_color(18, 18, 26)
                self.set_text_color(232, 232, 237)
                for i, h in enumerate(headers):
                    self.cell(col_widths[i], 7, h, 1, 0, 'C', True)
                self.ln()
                self.set_font('Helvetica', '', 7.5)
                self.set_text_color(26, 26, 46)
                if idx % 2 == 0:
                    self.set_fill_color(249, 250, 251)
                else:
                    self.set_fill_color(255, 255, 255)

            x_start = self.get_x()
            y_start = self.get_y()

            # Draw cells
            self.set_font('Helvetica', 'B', 7.5)
            self.cell(col_widths[0], row_h, str(num), 1, 0, 'C', True)

            self.set_font('Helvetica', '', 7.5)
            x_feat = self.get_x()
            self.multi_cell(col_widths[1], 4.2, feature, 0, 'L')
            y_after_feat = self.get_y()

            self.set_xy(x_feat + col_widths[1], y_start)
            self.set_font('Helvetica', '', 7)
            self.set_text_color(100, 100, 100)
            self.multi_cell(col_widths[2], 4.2, test, 0, 'L')
            y_after_test = self.get_y()

            self.set_text_color(26, 26, 46)

            # Checkbox
            self.set_xy(x_start + col_widths[0] + col_widths[1] + col_widths[2], y_start)
            self.cell(col_widths[3], row_h, '[ ]', 1, 0, 'C', True)

            # Draw bottom border
            self.set_draw_color(229, 231, 235)
            self.line(x_start, y_start + row_h, x_start + sum(col_widths), y_start + row_h)

            self.set_xy(x_start, y_start + row_h)

    def _count_lines(self, text, width):
        """Estimate number of lines text will take."""
        if not text:
            return 1
        # Rough estimate: ~4 chars per mm at font size 7.5
        chars_per_line = int(width * 3.8)
        if chars_per_line <= 0:
            return 1
        lines = len(text) / chars_per_line
        return max(1, int(lines) + 1)


def build_pdf():
    pdf = ChecklistPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title page
    pdf.set_font('Helvetica', 'B', 24)
    pdf.set_text_color(10, 10, 15)
    pdf.ln(20)
    pdf.cell(0, 15, 'SPEED TO LEAD v4', 0, 1, 'C')
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(99, 102, 241)
    pdf.cell(0, 12, 'PHASE 2 CHECKLIST', 0, 1, 'C')
    pdf.ln(5)
    pdf.set_font('Helvetica', '', 12)
    pdf.set_text_color(107, 114, 128)
    pdf.cell(0, 8, 'Client-Side Features & Service Delivery Verification', 0, 1, 'C')
    pdf.ln(10)

    # Info box
    pdf.set_fill_color(18, 18, 26)
    pdf.set_text_color(232, 232, 237)
    pdf.set_font('Helvetica', '', 10)
    box_y = pdf.get_y()
    pdf.rect(30, box_y, 150, 50, 'F')
    pdf.set_xy(35, box_y + 5)
    info_lines = [
        'Date: June 8, 2026',
        'Live URL: https://speed-to-lead-8tfi.onrender.com',
        'Test Credentials: dealer=premier-auto, user=admin',
        'Current Status: Phase 1 complete (222 tests, 317 leads, Twilio ON)',
        'Phase Focus: Client-side features & servicing clients at highest level',
    ]
    for line in info_lines:
        pdf.cell(140, 8, line, 0, 1, 'L')
        pdf.set_x(35)

    pdf.ln(15)

    # Stats
    pdf.set_text_color(26, 26, 46)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 8, 'Checklist Summary:', 0, 1)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, 'Section 1: Dealership Owner / General Manager  -  54 items', 0, 1)
    pdf.cell(0, 6, 'Section 2: Sales Team / Sales Reps  -  20 items', 0, 1)
    pdf.cell(0, 6, 'Section 3: Customer Experience  -  21 items', 0, 1)
    pdf.cell(0, 6, 'Section 4: System Health & Reliability  -  12 items', 0, 1)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 8, 'TOTAL: 107 verification items across 4 stakeholder perspectives', 0, 1)

    # =========================================================================
    # SECTION 1: DEALERSHIP OWNER / GM
    # =========================================================================
    pdf.add_page()
    pdf.section_title('SECTION 1: DEALERSHIP OWNER / GENERAL MANAGER')
    pdf.body_text('These features serve the person who pays for the product. They need to see ROI, manage their team, and trust the system.')

    # 1.1 Login & Auth
    pdf.subsection_title('1.1 Login & Authentication')
    pdf.checklist_table([
        (1, 'Secure login with dealer slug', 'POST /dashboard/login with valid slug+user+pw -> 302 to /dashboard/leads, session cookie set', ''),
        (2, 'Invalid credentials rejected', 'POST with wrong password -> 401 + "Invalid credentials" message', ''),
        (3, 'Unknown dealer slug rejected', 'POST with nonexistent slug -> 401 + "Unknown dealer slug"', ''),
        (4, 'Rate limiting on brute force', '5 failed logins from same IP -> 429 + "Too many attempts" for 15 min', ''),
        (5, 'Session expiry (24h)', 'Login, wait or tamper with cookie timestamp -> redirect to /login', ''),
        (6, 'Logout clears session', 'GET /dashboard/logout -> cookie deleted, redirect to /login', ''),
        (7, 'Unauthenticated access blocked', 'GET /dashboard/leads without cookie -> 303 redirect to /login', ''),
        (8, 'Cross-dealer data isolation', 'Login as premier-auto -> cannot view leads from another dealer by ID', ''),
    ])

    # 1.2 Lead Pipeline
    pdf.subsection_title('1.2 Lead Pipeline Overview')
    pdf.checklist_table([
        (9, 'Lead table renders with real data', 'GET /dashboard/leads -> HTML contains lead names, phones, statuses from DB', ''),
        (10, 'Stats cards show correct counts', 'total_leads, active_leads, appt_leads, sold_leads match DB queries', ''),
        (11, 'Status badges display correctly', 'Each lead shows colored badge (NEW=green, ASSIGNED=yellow, LOST=red)', ''),
        (12, 'Health indicators compute correctly', 'Hot (APPT_SET), Warm (<48h), Cold (<72h), Dead (>72h) - verify each color', ''),
        (13, 'Click lead row -> detail page', 'Click any row -> navigates to /dashboard/leads/{id} with correct data', ''),
        (14, '"No leads found" empty state', 'Dealer with zero leads -> shows message, not a crash', ''),
        (15, 'Lead timestamps render correctly', 'created_at shows as "Jun 08, 2026 02:30 PM" format', ''),
    ])

    # 1.3 Attention Widget
    pdf.subsection_title('1.3 Needs Attention Widget')
    pdf.checklist_table([
        (16, 'Unclaimed leads flagged', 'Lead ASSIGNED > 2h -> red "Unclaimed for Xh" card appears', ''),
        (17, 'Going-cold leads flagged', 'Lead ENGAGED > 48h -> yellow "No activity for X days" card', ''),
        (18, "Today's appointments shown", 'Appointment today -> blue calendar card with time', ''),
        (19, 'Failed deliveries flagged', 'Message with delivery_status=failed -> red X-circle card', ''),
        (20, 'Cards sorted by urgency', 'High urgency (unclaimed) appears before medium (cold)', ''),
        (21, '"All clear" state when empty', 'No items -> green checkmark + "All clear" message', ''),
        (22, 'Click card -> lead detail', 'Clicking attention card navigates to lead detail page', ''),
    ])

    # 1.4 Lead Detail
    pdf.subsection_title('1.4 Lead Detail & Timeline')
    pdf.checklist_table([
        (23, 'Lead info card displays', 'Name, phone, email, source, status, assigned rep all rendered', ''),
        (24, 'Unified timeline merges events + messages', 'State changes and messages appear chronologically in one view', ''),
        (25, 'Message direction indicators', 'Inbound vs outbound messages show different icons/colors', ''),
        (26, 'Message channel shown', 'Each message shows SMS, WhatsApp, or Email badge', ''),
        (27, 'AI-generated messages flagged', 'Messages with ai_generated=true show AI indicator', ''),
        (28, 'Delivery status visible', 'Each message shows delivery status (delivered/failed/sent)', ''),
        (29, 'Appointments section', 'Booked appointments show date, time, status', ''),
        (30, 'Reassign lead (HTMX)', 'POST /leads/{id}/reassign -> assigned_rep updated, toast shown', ''),
        (31, 'Update status (HTMX)', 'POST /leads/{id}/status -> lifecycle transition fires', ''),
        (32, 'Send message (HTMX)', 'POST /leads/{id}/messages -> Message record + SMS sent', ''),
        (33, 'Mark sold (HTMX)', 'POST /leads/{id}/mark-sold -> state=SOLD, redirect to leads', ''),
        (34, 'Mark lost (HTMX)', 'POST /leads/{id}/mark-lost -> state=LOST, redirect to leads', ''),
        (35, 'Schedule follow-up', 'POST /leads/{id}/follow-up -> LeadEvent with scheduled_for', ''),
    ])

    # 1.5 Stats
    pdf.subsection_title('1.5 Stats & Analytics')
    pdf.checklist_table([
        (36, 'Date range filter works', '?days=7,30,90 -> stats reflect only that window', ''),
        (37, 'Top stats cards correct', 'Total, Active, Conversion Rate, Appointments match DB', ''),
        (38, 'Avg response time computed', 'Shows human-readable time (e.g., "45s" or "3m 12s")', ''),
        (39, 'Response time color coding', '<60s=green, 60-300s=yellow, >300s=red CSS classes', ''),
        (40, '% Within 5 Minutes correct', 'Percentage = responded_in_5min / total_responded * 100', ''),
        (41, 'Conversion funnel renders', '8 stages (NEW->SOLD) as horizontal bars with counts', ''),
        (42, 'Funnel narrows correctly', 'NEW >= AUTO_REPLIED >= ... >= SOLD (or zeros)', ''),
        (43, 'Source breakdown table', 'Leads by source with total, conversion%, appt%', ''),
        (44, 'Source percentage bars render', 'Visual bars show relative volume per source', ''),
        (45, 'Rep performance leaderboard', 'Per-rep: assigned, engaged, appt_set, sold, lost, conv%', ''),
        (46, 'Leaderboard sorted by sold', 'Most sales first, gold/silver/bronze rank indicators', ''),
    ])

    # 1.6 Appointments
    pdf.subsection_title('1.6 Appointments Calendar')
    pdf.checklist_table([
        (47, 'Appointments list renders', 'GET /dashboard/appointments -> shows all with lead names', ''),
        (48, 'Today/week counts correct', 'today_count and week_count match actual appointments', ''),
        (49, 'Show rate computed', 'showed_count and no_show_pct from completed appointments', ''),
        (50, 'Status filter works', '?status=set,showed,no_show -> list filters correctly', ''),
        (51, 'Appointment detail links', 'Each appointment links to associated lead detail page', ''),
    ])

    # 1.7 Settings
    pdf.subsection_title('1.7 Settings & Configuration')
    pdf.checklist_table([
        (52, 'Dealer info displayed', 'Name, phone, address, AI persona loaded from config', ''),
        (53, 'Settings form renders', 'GET /dashboard/settings -> form fields populated', ''),
        (54, 'Settings save (if wired)', 'POST /dashboard/settings -> config updated, toast shown', ''),
    ])

    # =========================================================================
    # SECTION 2: SALES TEAM
    # =========================================================================
    pdf.add_page()
    pdf.section_title('SECTION 2: SALES TEAM / SALES REPS')
    pdf.body_text('These features serve the people on the floor who handle leads daily.')

    pdf.subsection_title('2.1 Team Management')
    pdf.checklist_table([
        (55, 'Team roster displays', 'GET /dashboard/team -> shows reps with names and phones', ''),
        (56, 'Add team member', 'POST /team with name+phone -> rep added, toast shown', ''),
        (57, 'Rep performance table', 'Each rep: assigned, engaged, appt_set, sold, lost, conv%', ''),
        (58, 'Reps without leads still show', 'Configured reps with zero leads appear in roster', ''),
        (59, 'Active rep count correct', 'Header shows unique reps (configured + with leads)', ''),
        (60, 'Leads today count', 'Leads created since midnight UTC', ''),
        (61, 'Overall conversion rate', 'total_sold / total_assigned * 100 as percentage', ''),
    ])

    pdf.subsection_title('2.2 Lead Assignment & Routing')
    pdf.checklist_table([
        (62, 'Round-robin assigns evenly', '3 reps, 6 leads -> each gets 2 (verify via DB)', ''),
        (63, 'WhatsApp claim ping sent', 'New lead -> WhatsApp message to assigned rep', ''),
        (64, 'Claim via reply "1"', 'Rep replies "1" -> state=CLAIMED, rep confirmed', ''),
        (65, 'Pass via reply "2"', 'Rep replies "2" -> lead reassigned to next rep', ''),
        (66, 'SLA timeout escalation', 'No claim in 5 min -> next rep, then manager', ''),
        (67, 'Inactive reps skipped', 'Inactive rep -> excluded from rotation', ''),
    ])

    pdf.subsection_title('2.3 Lead Interaction from Dashboard')
    pdf.checklist_table([
        (68, 'Send SMS from lead detail', 'Type message, send -> outbound Message + Twilio call', ''),
        (69, 'Message appears in timeline', 'After send, message shows as direction=outbound', ''),
        (70, 'Reassign to another rep', 'Select different rep -> assigned_rep updated', ''),
        (71, 'Status change via dashboard', 'Change status -> lifecycle transition fires', ''),
    ])

    # =========================================================================
    # SECTION 3: CUSTOMER EXPERIENCE
    # =========================================================================
    pdf.section_title('SECTION 3: THE CUSTOMER EXPERIENCE')
    pdf.body_text('These features are what the car buyer experiences. They are the product.')

    pdf.subsection_title('3.1 Auto-Reply System')
    pdf.checklist_table([
        (72, 'Instant auto-reply on SMS', 'Customer texts -> auto-reply within 60s mentioning vehicle', ''),
        (73, 'Auto-reply mentions dealer name', 'Reply includes dealership name from config', ''),
        (74, 'Auto-reply mentions vehicle', 'Reply references specific vehicle customer asked about', ''),
        (75, 'Auto-reply asks one clear question', 'Reply ends with question moving toward a visit', ''),
        (76, 'Lead appears in dashboard', 'After auto-reply, lead shows with state=AUTO_REPLIED', ''),
    ])

    pdf.subsection_title('3.2 AI Qualification & Booking')
    pdf.checklist_table([
        (77, 'AI qualifies timeline', '"Looking to buy this week" -> AI recognizes urgency', ''),
        (78, 'AI qualifies trade-in', 'Customer mentions trade-in -> AI asks about vehicle', ''),
        (79, 'AI qualifies financing', 'Customer asks about payments -> AI acknowledges safely', ''),
        (80, 'AI books appointment', 'Customer agrees to time -> Appointment created, APPT_SET', ''),
        (81, 'AI offers specific slots', '"Tuesday 2pm or Wednesday 10am" not "when works for you"', ''),
        (82, 'AI respects guardrails', 'Price negotiation -> AI deflects to rep', ''),
        (83, 'AI uses real inventory only', 'Mentioned car exists in Vehicle table', ''),
    ])

    pdf.subsection_title('3.3 After-Hours Mode')
    pdf.checklist_table([
        (84, 'After-hours detection', 'System identifies business vs after-hours from config', ''),
        (85, 'AI runs autonomously after hours', 'After-hours lead -> AI handles full conversation', ''),
        (86, 'Morning summary generated', 'After-hours leads -> summary for reps at start of business', ''),
    ])

    pdf.subsection_title('3.4 Compliance (CASL + PIPA BC)')
    pdf.checklist_table([
        (87, 'Opt-out honored immediately', '"STOP" -> confirmation sent, no further messages', ''),
        (88, 'Opt-out logged', 'STOP -> ConsentLog entry with timestamp and keyword', ''),
        (89, 'Opted-out customer ignored', 'Opted-out texts again -> no response', ''),
        (90, 'Quiet hours respected', 'No messages during quiet hours (default 9PM-8AM)', ''),
        (91, 'Sender identification', 'Every SMS includes dealer name + opt-out instructions', ''),
        (92, 'Consent capture', 'New lead -> consent recorded in ConsentLog', ''),
    ])

    # =========================================================================
    # SECTION 4: SYSTEM HEALTH
    # =========================================================================
    pdf.add_page()
    pdf.section_title('SECTION 4: SYSTEM HEALTH & RELIABILITY')

    pdf.subsection_title('4.1 Infrastructure')
    pdf.checklist_table([
        (93, 'Health endpoint live', 'GET /healthz -> 200 {"status":"ok","db":"ok"}', ''),
        (94, 'Readiness endpoint live', 'GET /readyz -> 200 {"status":"ready"}', ''),
        (95, 'No JS console errors', 'browser_console() on each page -> zero errors', ''),
        (96, 'Dark theme renders correctly', 'Background #0a0a0f, surface #12121a, accent #6366f1', ''),
        (97, 'Responsive on mobile', 'Sidebar collapses, content stacks on narrow viewport', ''),
        (98, 'HTMX partial updates work', 'Filters/search -> table updates without page reload', ''),
        (99, 'Sidebar navigation correct', 'All nav links route to correct pages', ''),
        (100, 'Active page highlighted', "Current page's nav item has distinct indicator", ''),
    ])

    pdf.subsection_title('4.2 Data Integrity')
    pdf.checklist_table([
        (101, 'LeadEvent append-only', 'State changes create events, never modify existing', ''),
        (102, 'Message records complete', 'Every SMS has Message record with direction/channel/body', ''),
        (103, 'Appointment records linked', 'Each appointment has valid lead_id foreign key', ''),
        (104, 'Dealer isolation verified', 'Query dealer A -> zero results from dealer B', ''),
    ])

    # =========================================================================
    # TESTING PROTOCOL
    # =========================================================================
    pdf.ln(5)
    pdf.section_title('TESTING PROTOCOL')

    pdf.subsection_title('Phase 2 Execution Order')
    pdf.bold_text('1. Automated tests first:')
    pdf.body_text('   pytest -q --tb=short  (all 222+ tests must pass)')
    pdf.bold_text('2. Browser walkthrough:')
    pdf.body_text('   Login -> click every page -> check console for errors')
    pdf.bold_text('3. HTMX interaction test:')
    pdf.body_text('   Click every button, fill every form, verify toast messages')
    pdf.bold_text('4. Data verification:')
    pdf.body_text('   Compare dashboard numbers against direct DB queries')
    pdf.bold_text('5. Mobile viewport test:')
    pdf.body_text('   Resize browser to 375px width, verify layout adapts')

    pdf.ln(3)
    pdf.subsection_title('Success Criteria')
    criteria = [
        'All 104 checklist items pass',
        'Zero JavaScript console errors on any page',
        'All HTMX interactions return 200 + show toast confirmation',
        'Dashboard numbers match direct DB queries',
        'Dark theme renders consistently across all pages',
        'No broken links or 404s in navigation',
    ]
    for c in criteria:
        pdf.body_text(f'  [  ]  {c}')

    pdf.ln(3)
    pdf.subsection_title('Notes')
    pdf.body_text('- Twilio is ON: real SMS will send during live-fire tests (items 72-76, 87-88)')
    pdf.body_text('- Use OUTBOUND_ENABLED=false for dashboard-only testing to avoid burning credits')
    pdf.body_text('- Items marked [FUTURE] in FEATURES.md are out of scope for Phase 2')

    # Save
    out_path = r'C:\Users\manav.LAPTOP-TTEINC4O\Desktop\Speed to Lead v4\docs\PHASE2_CHECKLIST.pdf'
    pdf.output(out_path)
    print(f'PDF saved to: {out_path}')
    return out_path

if __name__ == '__main__':
    build_pdf()
