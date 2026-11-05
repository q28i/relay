# 05 — UI/UX Overhaul & Token Design System

## 1. Visual Philosophy & Design Principles

The user interface was built to depart completely from generic AI-generated templates. Rather than relying on default browser form controls or unstyled dark-mode inversions, the interface follows four strict design tenets:
1. **Semantic Accessibility First**: Every interactive control uses standard HTML semantics (`<input type="radio">`, `<fieldset>`, `<button>`, `role="radiogroup"`), supporting full keyboard tab order and screen reader announcements.
2. **Deterministic Tonal Steps**: Dark mode is not an inverted white palette. It uses a bespoke graphite-and-onyx scale with controlled contrast ratios exceeding WCAG AAA standards.
3. **Authentic Domain Familiarity**: The WhatsApp conversation preview faithfully mirrors real WhatsApp Web and mobile layouts (bubble shapes, SVG double ticks, micro-dot background patterns).
4. **Contextual Action Disclosure**: Action controls appear only where relevant (e.g., embedded profile launch buttons reveal inside the selected connection model card).

---

## 2. Complete Design Token Matrix

The design system is implemented in [`backend/static/styles.css`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/static/styles.css) using CSS Custom Properties:

| Design Token | Light Theme (Default) | Void Theme (`[data-theme="void"]`) | Purpose / Component Target |
| :--- | :--- | :--- | :--- |
| `--body-bg` | `#FBFBFA` | `#08090A` (true charcoal black) | Page foundation background |
| `--surface-bg` | `#FFFFFF` | `#121417` (tonal graphite step 1) | Primary cards, modals, sidebars |
| `--surface-subtle` | `#F4F4F5` | `#16191D` (tonal graphite step 2) | Table headers, secondary toolbars |
| `--surface-elevated` | `#E4E4E7` | `#1C2025` (tonal graphite step 3) | Hover states, active segmented buttons |
| `--border-color` | `#E4E4E7` | `#22262B` (low-contrast graphite) | Structural card borders and dividers |
| `--border-hover` | `#D4D4D8` | `#2E343B` | Interactive hover borders |
| `--text-primary` | `#18181B` | `#EDEDED` (warm off-white) | Primary headings and message text |
| `--text-secondary` | `#3F3F46` | `#9CA3AF` (cool grey) | Subtitles, labels, descriptions |
| `--text-muted` | `#71717A` | `#737B87` (muted slate) | Timestamps, placeholder texts |
| `--primary` | `#0F766E` (deep teal) | `#0D9488` (luminous emerald) | Primary buttons and brand marks |
| `--primary-subtle` | `#F0FDFA` | `rgba(13, 148, 136, 0.14)` | Active pill backgrounds, subtle glows |
| `--primary-glow` | `none` | `0 0 16px rgba(13, 148, 136, 0.25)` | Focused card border glow |
| `--success` | `#15803D` | `#10B981` (emerald) | Connected indicators, sent badges |
| `--warning` | `#B45309` | `#F59E0B` (amber) | QR required, pacing cautions |
| `--danger` | `#B91C1C` | `#EF4444` (muted coral) | Error banners, delete buttons |

---

## 3. Zero-Flash Theme Bootstrapping

To eliminate white flashes during page reload when Void mode is active, an inline synchronous IIFE is evaluated in `<head>` prior to CSS parsing in [`backend/static/index.html`](file:///c:/Users/Rift/Documents/Antigravity%20ide/whatsapp%20automation/backend/static/index.html):

```html
<script>
  (function() {
    try {
      var saved = localStorage.getItem('theme') || 'system';
      var effective = saved;
      if (saved === 'system') {
        effective = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'void' : 'light';
      }
      document.documentElement.setAttribute('data-theme', effective);
    } catch(e) {}
  })();
</script>
```

---

## 4. Accessible Interactive Choice Controls

### The Radio Card Component
Previously, theme options, connection models, and campaign pace choices were plain clickable `<div>` tags lacking screen reader accessibility and keyboard focus. They have been replaced with the **Semantic Radio Card** pattern:

```html
<label class="radio-card theme-option-card" id="theme-card-void">
  <input type="radio" name="theme-choice" value="void" class="radio-card-input" id="radio-theme-void">
  <div class="radio-card-header">
    <div class="radio-card-title-group">
      <span class="radio-card-title">Void (Onyx)</span>
      <span class="radio-card-desc">High-contrast near-black workspace</span>
    </div>
    <span class="radio-indicator" aria-hidden="true"></span>
  </div>
</label>
```

### Visual & Interactive Highlights:
1. **Visually Hidden, Accessible Input**: The native `<input type="radio">` is positioned with zero opacity and 1px dimensions. It receives native browser focus events, while custom CSS renders the outer card and `.radio-indicator` dot.
2. **High-Contrast Focus Outlines**:
   ```css
   .radio-card:has(.radio-card-input:focus-visible),
   .radio-card.has-focus {
     outline: 2px solid var(--primary);
     outline-offset: 2px;
   }
   ```
3. **Dynamic Embedded Action Trays**:
   Selecting the **Dedicated Relay Session** card automatically slides open the dedicated action buttons (`Open dedicated session`, `Check session`), while selecting **Existing Browser Profile** reveals the profile picker trigger and connection tester.
4. **Instant Persistence**: Theme selection updates `localStorage` and triggers a confirmation toast (*"Void theme applied."*).

---

## 5. Authentic WhatsApp Web Conversation Preview

Under the **Messages** and **Campaigns** tabs, a high-fidelity WhatsApp preview pane simulates live message delivery:

```
┌─────────────────────────────────────────────────────────────┐
│ 👤 Alex Rivera                            📞  📹  🔍  ⋮     │
│    online                                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│       ┌──────────────────────────────────────────────┐      │
│       │ Hello Alex Rivera! 👋                        │      │
│       │ Your VIP shipment #4829 has been processed.  │      │
│       │                      17:28 ✓✓                │      │
│       └──────────────────────────────────────────────┘      │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ 📎  Type a message                                     🎤  │
└─────────────────────────────────────────────────────────────┘
```

### Key Technical Details:
- **Authentic Chat Backgrounds**:
  - Light mode: Canvas `#EFEAE2` with subtle doodle texture overlay.
  - Void mode: Canvas `#0B141A` with micro-radial dark pattern `#1B2831`.
- **Bubble Color Matching**:
  - Outgoing Light: `#D9FDD3` with `#111B21` text.
  - Outgoing Void: `#005C4B` with `#E9EDEF` text.
  - Incoming Light: `#FFFFFF`; Incoming Void: `#202C33`.
- **Dynamic Variable Interpolation**: Replaces `{{name}}`, `{{phone}}`, and custom fields live as the operator types.
- **Responsive View Toggle**: One-click toggle between **Desktop Preview** (wide chat layout) and **Mobile Phone Preview** (device bezel frame).
- **Media Asset Preview**: Inline rendering of attached images, PDF document cards with download badges, and failed-media fallback badges.

---

## 6. Custom File Upload Drag-and-Drop Dropzone

Replaced native unstyled browser `<input type="file">` controls with a custom dropzone:
- Drag-and-drop file target with hover highlight states.
- File type validation icons (Images: PNG, JPG; Documents: PDF, XLSX).
- File size badge and one-click file removal button.

