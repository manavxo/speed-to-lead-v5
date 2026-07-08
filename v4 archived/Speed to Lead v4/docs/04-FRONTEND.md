# Frontend — Dashboard Design System

## Design System

All styles are defined as CSS custom properties in `app/dashboard/templates/base.html`.

### Color Palette

```css
:root {
    /* Background */
    --bg: #0a0a0f;              /* Near-black, main background */
    --bg-surface: #12121a;      /* Cards, panels, sidebar */
    --bg-elevated: #1a1a25;     /* Hover states, raised elements */

    /* Borders */
    --border: rgba(255, 255, 255, 0.06);
    --border-hover: rgba(255, 255, 255, 0.1);

    /* Text */
    --text-primary: #e8e8ed;    /* Main text */
    --text-secondary: #6b7280;  /* Labels, metadata */
    --text-muted: #4b5563;      /* Disabled, hints */

    /* Accent */
    --accent: #6366f1;          /* Indigo — buttons, links, active states */
    --accent-hover: #818cf8;    /* Lighter indigo on hover */
    --accent-subtle: rgba(99, 102, 241, 0.1);  /* Background tint */

    /* Status Colors */
    --success: #22c55e;         /* Green — new leads, positive */
    --warning: #eab308;         /* Yellow — waiting, attention needed */
    --error: #ef4444;           /* Red — stale, lost, errors */
    --info: #3b82f6;            /* Blue — informational */
    --purple: #a855f7;          /* Purple — special states */
    --cyan: #06b6d4;            /* Cyan — accent variety */
    --gold: #f59e0b;            /* Gold — premium/highlight */

    /* Shadows */
    --shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.4);

    /* Layout */
    --sidebar-width: 240px;
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;

    /* Transitions */
    --transition: all 0.2s ease;
}
```

### Typography

- **Font:** Inter (loaded from Google Fonts)
- **Body size:** 14px
- **Dense UI size:** 13px
- **Line height:** 1.5
- **Font weights:** 400 (regular), 500 (medium), 600 (semibold)
- **Letter spacing:** -0.01em to -0.02em for headings

---

## Component Specs

### Buttons

| Class          | Background          | Text    | Border              | Use case          |
| -------------- | ------------------- | ------- | ------------------- | ----------------- |
| `.btn-primary` | `var(--accent)`     | white   | `var(--accent)`     | Main actions      |
| `.btn-secondary` | `var(--bg-elevated)` | `var(--text-primary)` | `var(--border)` | Secondary actions |
| `.btn-ghost`   | transparent         | `var(--text-secondary)` | transparent | Tertiary actions  |
| `.btn-danger`  | `rgba(239,68,68,0.1)` | `var(--error)` | `rgba(239,68,68,0.2)` | Destructive actions |

Sizes: `.btn-sm` (5px 10px, 12px), default (8px 16px, 13px), `.btn-lg` (10px 20px, 14px)

### Cards

```html
<div class="card">
    <div class="card-header">
        <span class="card-title">Title</span>
    </div>
    <div class="card-body">
        Content here
    </div>
</div>
```

- Background: `var(--bg-surface)`
- Border: `1px solid var(--border)`
- Border radius: `var(--radius-md)` (8px)

### Badges

```html
<span class="badge badge-new">NEW</span>
<span class="badge badge-assigned">ASSIGNED</span>
<span class="badge badge-engaged">ENGAGED</span>
<span class="badge badge-appt">APPT SET</span>
<span class="badge badge-sold">SOLD</span>
<span class="badge badge-lost">LOST</span>
```

| Badge            | Background                          | Color         |
| ---------------- | ----------------------------------- | ------------- |
| `.badge-new`     | `rgba(34, 197, 94, 0.12)`         | `--success`   |
| `.badge-assigned` | `rgba(234, 179, 8, 0.12)`        | `--warning`   |
| `.badge-engaged` | `rgba(99, 102, 241, 0.12)`        | `--accent`    |
| `.badge-appt`    | `rgba(168, 85, 247, 0.12)`        | `--purple`    |
| `.badge-sold`    | `rgba(34, 197, 94, 0.15)`         | `--success`   |
| `.badge-lost`    | `rgba(239, 68, 68, 0.12)`         | `--error`     |

The `.badge-new` class includes a pulsing green dot animation.

### Inputs

```html
<input class="input" type="text" placeholder="Search leads...">
<select class="select"><option>...</option></select>
```

- Background: `var(--bg)`
- Border: `1px solid var(--border)`
- Focus: `border-color: var(--accent)` + `box-shadow: 0 0 0 3px rgba(99,102,241,0.1)`

---

## Layout Structure

```
┌─────────────────────────────────────────────┐
│ .app-layout (flex, 100vh)                   │
│ ┌──────────┐ ┌────────────────────────────┐ │
│ │ .sidebar  │ │ .main-content              │ │
│ │ 240px     │ │ ┌────────────────────────┐ │ │
│ │           │ │ │ .top-bar (56px height) │ │ │
│ │ Logo      │ │ ├────────────────────────┤ │ │
│ │ Dealer    │ │ │ .content-area          │ │ │
│ │           │ │ │ (scrollable, 24px pad) │ │ │
│ │ Nav       │ │ │                        │ │ │
│ │ - Leads   │ │ │                        │ │ │
│ │ - Team    │ │ │                        │ │ │
│ │ - Settings│ │ │                        │ │ │
│ │ - Stats   │ │ │                        │ │ │
│ │           │ │ │                        │ │ │
│ │ Footer    │ │ │                        │ │ │
│ └──────────┘ │ └────────────────────────┘ │ │
│              └────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

- Sidebar collapses on mobile (hidden by default, toggle via hamburger)
- Mobile: sidebar becomes a bottom tab bar pattern
- Content area scrolls independently

---

## The 7 Templates

### 1. base.html — Layout Shell
- Sidebar with navigation (Leads, Team, Settings, Stats)
- Top bar with page title and action buttons
- CSS custom properties (all design tokens)
- HTMX script tag
- Inter font from Google Fonts
- Responsive: sidebar collapses on mobile

### 2. login.html — Authentication
- Standalone page (no sidebar)
- Username + password form
- POST to login endpoint
- Uses the same dark theme

### 3. leads.html — Lead Pipeline Overview
- Stats cards at top (total, active, appointments, sold)
- Lead table: name, source, status badge, assigned rep, time since inquiry
- Click any row → navigates to `/dashboard/leads/{id}`
- Filter by status (tabs or dropdown)
- Data: passed from `GET /dashboard/leads` route

### 4. lead_detail.html — Lead Detail + Timeline
- Lead info card (name, phone, email, source, status, assigned rep)
- Unified timeline: state change events + messages merged chronologically
- Each message shows direction (inbound/outbound), channel, body, delivery status
- AI-generated messages are flagged
- Data: passed from `GET /dashboard/leads/{lead_id}` route

### 5. team.html — Sales Team Management
- List of reps with name, WhatsApp number, active status
- Add/remove reps
- Toggle active/inactive
- (Planned) Set round-robin weights

### 6. settings.html — Dealer Settings
- Dealer name, timezone, hours
- AI persona, goal, guardrails
- Channel numbers (SMS, WhatsApp)
- Compliance settings (consent text, opt-out keywords, quiet hours)
- (Planned) Save changes via form POST

### 7. stats.html — Stats & Reporting
- Leads per week (chart placeholder)
- Average response time
- Conversion funnel
- Per-rep performance
- Lead source breakdown
- (Planned) Real data queries

---

## HTMX Patterns

### Load Content Without Page Refresh

```html
<!-- Click a lead row, load detail in a target div -->
<tr hx-get="/dashboard/leads/{{ lead.id }}"
    hx-target="#detail-panel"
    hx-swap="innerHTML">
    <td>{{ lead.name }}</td>
</tr>
```

### Inline Status Update

```html
<!-- Change lead status with a button click -->
<button hx-post="/dashboard/leads/{{ lead.id }}/status"
        hx-vals='{"status": "LOST"}'
        hx-target="#lead-status-{{ lead.id }}"
        hx-swap="outerHTML"
        class="btn btn-danger btn-sm">
    Mark Lost
</button>
```

### Polling for Updates

```html
<!-- Auto-refresh the leads list every 30 seconds -->
<div hx-get="/dashboard/leads"
     hx-trigger="every 30s"
     hx-swap="innerHTML">
    <!-- lead table content -->
</div>
```

### Form Submission

```html
<!-- Submit settings form without page reload -->
<form hx-post="/dashboard/settings"
      hx-target="#settings-result"
      hx-swap="innerHTML">
    <input class="input" name="dealer_name" value="{{ dealer.name }}">
    <button type="submit" class="btn btn-primary">Save</button>
</form>
<div id="settings-result"></div>
```

### Loading Indicator

```html
<!-- Show spinner while content loads -->
<div hx-get="/dashboard/stats"
     hx-trigger="load"
     hx-indicator="#loading">
    <div id="loading" class="htmx-indicator">Loading...</div>
</div>
```

CSS for the indicator:
```css
.htmx-indicator {
    display: none;
}
.htmx-request .htmx-indicator {
    display: inline-block;
}
.htmx-request.htmx-indicator {
    display: inline-block;
}
```
