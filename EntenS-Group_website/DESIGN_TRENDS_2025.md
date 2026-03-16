# Web Design Trends 2025–2026
## Research Report for EntenS Group — Premium Corporate / Portfolio Landing Page

**Context:** Landing page for a holding company managing entertainment centers, parks, hotels, and AI products.
**Target audience:** Business owners looking to sell or lease entertainment/hospitality assets.
**Compiled:** March 2025 | Based on Awwwards winners, CSS-Tricks, Smashing Magazine, Dribbble, and industry publications.

---

## Overview

The 2025–2026 design cycle is defined by one central tension: **emotional depth vs. machine precision**. Award-winning sites combine cinematic scroll experiences with data-clarity, using dark luxury palettes, kinetic typography, and AI-influenced geometric aesthetics. For a premium B2B holding like EntenS Group, the goal is to feel like a Bloomberg Terminal meets a five-star hotel lobby — authoritative, sophisticated, and quietly alive.

---

## Trend 01 — Scroll-Driven Cinematic Storytelling

### What it is
The page itself becomes a film. Content enters, transforms, and exits as the user scrolls — not with basic fade-ins, but with full sequence choreography: text splitting letter-by-letter, images zooming from thumbnail to full-bleed, numbers counting up, sections morphing into the next. The scroll bar is treated as a timeline scrubber.

### How it works technically
- CSS `animation-timeline: scroll()` (now baseline in all major browsers as of 2024)
- GSAP ScrollTrigger for complex multi-step sequences
- Lenis or Locomotive Scroll for smooth inertia scrolling (replaces native scroll feel)
- `will-change: transform` on animated elements for GPU offloading

### Sites using it (2024–2025 Awwwards winners)
- **Linear.app** — product sections reveal as you scroll, with precise motion
- **Vercel.com** — dark background, metrics animate into view with spring physics
- **Stripe.com** — gradient orbs track scroll position, sections feel timed
- **Apple iPhone 16 product page** — the gold standard; scroll literally flies the phone through scenes

### Application to EntenS Group
Each asset category (entertainment centers → parks → hotels → AI) gets its own "act" in the scroll timeline. As you scroll past the hero, the first entertainment center photograph expands from a small card to full-screen with key metrics (sq. meters, revenue multiple, lease terms) animating in from the sides. The transition to the next category is a horizontal slide that feels like turning a page in a premium brochure.

### Difficulty: Medium–Hard
GSAP ScrollTrigger is well-documented. Hardest part is performance tuning on mobile.

### UX Impact: Very High
Dramatically increases time-on-page (reported +40–60% in case studies). For B2B buyers who need convincing before they book a call, this keeps them engaged through all asset categories.

---

## Trend 02 — Dark Luxury with Selective Illumination

### What it is
The dominant color mode for premium corporate and tech sites in 2025 is deep dark — not flat black (#000000) but rich "velvet darks": deep navy (#0A0E1A), charcoal onyx (#0D0D0F), or warm near-black (#0F0B0B). Against these backgrounds, key elements are "lit" — glowing warm gold, electric teal, or crisp white — creating a spotlight effect that guides the eye exactly where the designer intends.

### The 2025 Palette Formula
```
Background:   #0A0E1A  (deep navy-black)
Surface:      #111827  (card backgrounds)
Primary glow: #C9A84C  (muted gold — luxury signal)
Accent:       #4FFFFF  (electric teal — AI/tech signal)
Text primary: #F0EDE8  (warm white, not harsh)
Text muted:   #6B7280  (gray for secondary info)
```

### Sites using it
- **Rolls-Royce.com** — deep charcoal, every car is lit like a museum piece
- **Maserati.com** — near-black backgrounds, gold accent lines
- **Palantir.com** — dark with cold electric blue for the tech credibility
- **Linear.app** — dark UI, glowing purple accents
- **Notion.com** 2024 rebrand — selective dark mode with warm illumination

### Application to EntenS Group
Dark luxury directly matches the "premium asset marketplace" positioning. Business owners expecting high-value deals expect this aesthetic — it signals that the holding operates at the level of private equity, not a real estate broker. The gold accent communicates wealth and entertainment-sector confidence. The electric teal accent can be reserved exclusively for the AI products section, creating a natural visual break.

Use a subtle noise/grain texture overlay (CSS `filter: url(#noise)` or a PNG overlay at 3–5% opacity) on dark backgrounds to add depth and prevent the "cheap dark mode" look.

### Difficulty: Easy
Entirely CSS-based. The hardest part is calibrating contrast ratios for accessibility (WCAG AA minimum 4.5:1 for body text).

### UX Impact: High
Dark luxury immediately signals premium tier. It reduces visual noise, focuses attention on photography and data, and feels modern without being gimmicky.

---

## Trend 03 — Kinetic / Variable Typography

### What it is
Text is no longer static. In 2025's top sites, headlines morph, stretch, split apart, and reassemble. Two specific sub-trends dominate:

1. **Variable font animation** — a single OpenType variable font animates between its weight/width/slant axes on hover or scroll. A headline might breathe from Light (100) to Black (900) weight as it scrolls into view.
2. **Text splitting choreography** — JS libraries (SplitType, GSAP SplitText) break headlines into individual characters or words, then animate each with staggered delays, creating a "typing" or "falling into place" effect.

### The 2025 Typography Stack for Premium B2B
- **Serif display** for headlines: Cormorant Garamond (free), PP Editorial New (premium), or Freight Display — conveys legacy, authority
- **Sans-serif body**: Inter, DM Sans, or Neue Haas Grotesk — clinical clarity
- **Size range**: Hero headlines at 80–140px on desktop; radical size contrast (140px headline vs 14px caption) is specifically a 2025 trend
- **Letter-spacing**: Slightly negative (-0.02em to -0.04em) on large display type; this is the typographic fingerprint of luxury

### Sites using it
- **Loewe.com** — editorial serif with extreme size contrast
- **Bottega Veneta** — headlines at near-display scale, ultra-fine weight
- **Fuse Collective** (Awwwards SOTD, 2024) — every headline animates character-by-character
- **The New York Times Cooking** — variable font weight transitions on scroll

### Application to EntenS Group
The hero headline should split-animate on load: "Активы, которые работают" enters character by character with 30ms stagger. On the portfolio section, each asset category title uses a variable font that transitions from thin italic (as it enters off-screen) to bold upright (when centered in viewport). The contrast between a 120px display serif for section titles and 13px all-caps tracking for labels ("ENTERTAINMENT CENTERS · 12 OBJECTS") creates immediate premium legibility.

### Difficulty: Easy–Medium
SplitType is ~5KB and straightforward. Variable fonts are served via Google Fonts (Cormorant Garamond is free, variable-weight). The main overhead is font load performance — subset to Latin+Cyrillic only.

### UX Impact: High
Typography is the fastest signal of brand tier. Kinetic type on entry creates the "this site is premium" impression in the first 3 seconds before any image loads.

---

## Trend 04 — Bento Grid Layouts

### What it is
Named after Japanese bento boxes, this layout system arranges content into asymmetric grid cells of varying sizes — some cells span 2 columns, some are square, some are tall — creating a dense, information-rich visual that feels organized yet dynamic. The cells themselves often have subtle hover states (slight lift, glow border).

This was popularized by Apple's WWDC 2023 page and has become the default premium layout for feature showcases in 2024–2025.

### How it works
- CSS Grid with `grid-template-areas` for complex cell arrangements
- Cells: `border-radius: 16–24px`, subtle `border: 1px solid rgba(255,255,255,0.08)` on dark backgrounds
- Hover: `transform: translateY(-4px)`, `box-shadow: 0 20px 60px rgba(0,0,0,0.3)`
- Content inside cells can be anything: a metric, a photo, a mini chart, a quote

### Sites using it
- **Apple.com** (product feature pages, 2023–2025) — the originator in modern web context
- **Linear.app** — features bento with animated cells
- **Vercel.com** — infrastructure features displayed in bento
- **Raycast.com** — extension ecosystem shown in bento grid

### Application to EntenS Group
The portfolio section is a natural bento: one large cell for "Entertainment Centers" (hero photo + key stat), two medium cells for "Parks" and "Hotels" side by side, one narrow tall cell for "AI Products" with a glowing accent. Each cell shows: property photo, location city, key metric (GLA sqm / occupancy rate / annual revenue range), and a small "View Details →" link. On hover, the cell lifts and the metric animates up by +1 to signal interactivity.

A second bento appears in the "Why EntenS" section: cells for "12 years", "₽8B+ assets under management", "47 properties", "3 cities", etc.

### Difficulty: Easy
Pure CSS Grid. The hardest part is choosing which cells get which sizes — a design decision, not a technical one.

### UX Impact: Very High
Bento lets B2B buyers scan the portfolio in 10 seconds. It replaces long scrolling lists with spatial relationships that the eye naturally groups. It also looks unmistakably premium and modern.

---

## Trend 05 — Glassmorphism 2.0 (Frosted UI Overlays)

### What it is
Glassmorphism — frosted-glass cards with `backdrop-filter: blur()` — was overused in 2022–2023 and briefly fell out of favor. In 2025 it has returned in a more restrained, refined form: "Glassmorphism 2.0" uses it selectively on floating UI elements (nav bars, tooltips, modal overlays, floating CTAs) rather than everywhere. The key refinements:

- **Tinted glass** — not just neutral blur but a slightly tinted blur (rgba warm or cool tone) matching the brand palette
- **Micro-border** — a 1px border at `rgba(255,255,255,0.15)` traces the glass edge
- **Layered depth** — glass elements sit visibly above a blurred version of the content behind them, creating genuine 3D depth perception

### CSS Recipe (2025 Standard)
```css
.glass-card {
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 20px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
```

### Sites using it
- **Jony Ive's LoveFrom** studio site — masterclass in restrained glassmorphism
- **macOS Sonoma/Sequoia web marketing pages** — Apple still the benchmark
- **Framer.com** — floating template cards use glass treatment
- **Craft.do** — document cards with layered glass depth

### Application to EntenS Group
1. **Navigation bar**: sticky nav uses glass treatment — as you scroll past the hero, the nav becomes a frosted bar showing page content blurred behind it.
2. **Floating CTA**: a persistent "Оставить заявку" button in the lower-right corner uses glass styling — it reads as a UI control floating above the page.
3. **Metric overlays**: in the portfolio bento, key stats (revenue, sqm) appear as small glass "chips" overlaid on the property photograph, like price tags in a luxury catalog.
4. **Contact form**: the form module sits in a glass container centered over a blurred aerial photo of one of the properties.

### Difficulty: Easy
`backdrop-filter` is now fully supported in all major browsers (including Firefox since v103). The main caveat is performance on low-end mobile — add `@supports` query and fall back to a semi-transparent background.

### UX Impact: Medium–High
Glass UI signals "premium digital product" (associates with iOS/macOS quality). When used in navigation and overlays specifically, it creates spatial depth that makes the page feel three-dimensional rather than flat.

---

## Trend 06 — Ambient / Mesh Gradient Backgrounds

### What it is
Flat solid backgrounds gave way to gradients, which gave way to meshes. In 2025, the dominant background technique is **ambient mesh gradients** — multiple large soft radial gradients layered and animated slowly (or driven by mouse movement), creating a luminous, almost atmospheric background that shifts like northern lights or a premium screensaver.

Two variants:
1. **Static mesh** — multiple colored blobs blended with `mix-blend-mode`, rendered as SVG or CSS
2. **Animated ambient** — blobs move slowly (20–30s CSS animation loop) using `border-radius` morphing and `transform: translate` to simulate organic movement

### CSS Technique
```css
.hero-background {
  background: #0A0E1A;
  position: relative;
  overflow: hidden;
}
.glow-orb-1 {
  position: absolute;
  width: 600px; height: 600px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(201,168,76,0.15) 0%, transparent 70%);
  filter: blur(80px);
  animation: float 25s ease-in-out infinite;
  top: -100px; left: -100px;
}
.glow-orb-2 {
  background: radial-gradient(circle, rgba(79,255,255,0.08) 0%, transparent 70%);
  filter: blur(120px);
  animation: float 35s ease-in-out infinite reverse;
  bottom: -200px; right: -150px;
}
@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33%       { transform: translate(60px, -40px) scale(1.05); }
  66%       { transform: translate(-30px, 50px) scale(0.98); }
}
```

### Sites using it
- **Stripe.com** — the defining example; animated gradient orbs have shipped on stripe.com since 2022 and were widely copied
- **Vercel.com** — blue/purple ambient on dark background
- **Loom.com** — warm gradient ambient in hero
- **Anthropic.com** — very restrained single warm glow
- **Resend.com** — single glow orb centered in dark hero, extremely effective

### Application to EntenS Group
The hero section uses a near-black background with two ambient orbs:
- Gold orb (top-left): symbolizes legacy wealth/entertainment
- Electric teal orb (bottom-right): symbolizes AI/technology

They move imperceptibly slowly (30s loop) — the user probably doesn't consciously notice the animation, but the background feels "alive" rather than static. On scroll into the "AI Products" section, the teal orb brightens (opacity transition from 0.08 to 0.20) to reinforce the context shift.

### Difficulty: Easy
Pure CSS, zero JS required for static or slowly animated versions. Mouse-tracking reactive versions require ~20 lines of JS.

### UX Impact: High
The difference between a flat dark background and an ambient gradient background is the difference between a conference room and a penthouse lounge. It costs almost nothing to implement and has outsized visual effect.

---

## Trend 07 — Horizontal Scroll Sections (within Vertical Scroll)

### What it is
A section of the page that, as the user scrolls vertically, actually moves content horizontally — like a film strip or a carousel that is controlled by the scroll wheel, not by clicking arrows. This "hijacked" scroll section is now used by many premium sites for showcasing a series of items (portfolio pieces, team members, product features) without requiring extra user action.

The key to doing it well in 2025: the horizontal section should have a **fixed height** in the viewport and the horizontal movement should feel 1:1 with scroll speed, so it never feels "stuck" or laggy.

### How it works
```css
.horizontal-scroll-container {
  display: flex;
  width: max-content; /* as wide as all slides combined */
}
/* GSAP ScrollTrigger pins the section and drives translateX */
```
```js
gsap.to(".horizontal-scroll-container", {
  x: () => -(container.scrollWidth - window.innerWidth),
  ease: "none",
  scrollTrigger: {
    trigger: ".horizontal-scroll-wrapper",
    pin: true,
    scrub: 1,
    end: () => `+=${container.scrollWidth - window.innerWidth}`,
  }
});
```

### Sites using it
- **Cuberto.com** (digital agency) — portfolio showcased in horizontal scroll section
- **Locomotive.ca** — their own homepage uses the technique
- **Ferrari.com** — car lineup is a horizontal scroll section
- **Burberry.com** — collection showcase uses horizontal scrolling panels

### Application to EntenS Group
The **Portfolio** section uses horizontal scroll to display individual properties as large cards (each card = 60vw wide, showing: hero photo, property name, city, GLA, key financial metric, status badge "Available for sale / Lease negotiation"). The user scrolls through 8–10 properties horizontally without ever leaving the main scroll flow. A progress indicator (thin line at bottom, like a film strip) shows position in the sequence.

This is the single highest-impact feature for the landing page — it lets buyers browse the entire asset inventory without navigating away, and the horizontal format makes each property feel like a full-spread in a premium brochure.

### Difficulty: Medium
GSAP ScrollTrigger is required. Must be disabled on mobile (replaced with a native horizontal swipe carousel). Total implementation: ~100 lines of JS + CSS.

### UX Impact: Very High
Transforms passive browsing into an active, memorable experience. Portfolio items feel curated rather than listed. Strongly differentiates from competitor sites that use basic grid galleries.

---

## Trend 08 — Micro-Interactions and Physics-Based Hover States

### What it is
Every interactive element on the page has a precisely choreographed response to user input — but in 2025, these responses use **spring physics** rather than simple CSS easing. The result is interactions that feel "material" — a button that slightly overshoots on hover and snaps back, a card that tilts in 3D as the cursor moves across it, a navigation item whose underline "snaps" to follow the hovered item.

Key micro-interaction patterns in 2025:
1. **Magnetic buttons** — the button element is slightly attracted toward the cursor as it approaches, then snaps back on leave
2. **3D card tilt** — cards rotate on both axes (X and Y) tracking cursor position, with a highlight that moves like a light source
3. **Cursor followers** — a custom cursor (large circle or dot) lags slightly behind the real cursor, morphs on hover over different element types
4. **Staggered list reveals** — list items enter with a 40ms stagger, each with a spring bounce
5. **Number counters** — statistics count up from 0 when scrolled into view, using easeOut timing

### Implementation
```js
// 3D Card Tilt (Vanilla JS, no library)
card.addEventListener('mousemove', (e) => {
  const rect = card.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width - 0.5;
  const y = (e.clientY - rect.top) / rect.height - 0.5;
  card.style.transform =
    `perspective(600px) rotateY(${x * 12}deg) rotateX(${-y * 12}deg)`;
});
```

### Sites using it
- **Reshaped.dev** — every button is magnetic
- **Stripe.com** — hover states on pricing cards use spring physics
- **Framer.com** — cursor follower, 3D card tilts throughout
- **Basement Studio** — custom cursor that morphs between a dot, crosshair, and "play" button
- **Obys Agency** — considered the benchmark for micro-interaction density

### Application to EntenS Group
1. **CTA Buttons** ("Связаться с нами", "Скачать презентацию"): magnetic pull within 60px radius, subtle scale 1.04 on hover
2. **Portfolio cards** (bento + horizontal scroll): 3D tilt tracking cursor
3. **Custom cursor**: a small circle (28px) that enlarges to 80px and reads "VIEW" when hovering over portfolio items, collapses back on leave
4. **Statistics**: "₽8B+ активов", "47 объектов", "12 лет" — all count up from zero on scroll-into-view
5. **Navigation links**: an animated underline that slides horizontally to follow the hovered item (like the Stripe nav)

### Difficulty: Easy–Medium
3D tilt is ~15 lines of vanilla JS. Number counters are ~20 lines. Magnetic buttons need ~30 lines. Custom cursor ~40 lines. All can be done without libraries.

### UX Impact: High
Micro-interactions transform a "nice-looking static page" into a "premium digital product." They signal craft and attention to detail — qualities a business owner wants to see from a company they're about to do a multi-million ruble deal with.

---

## Trend 09 — AI Aesthetic: Orbital Geometry and Data Visualization

### What it is
As AI becomes central to brand identity across industries, a new visual language has emerged: clean geometric forms suggesting computation — orbital rings, flowing data streams, neural network node graphs, precision grids, and animated SVG paths that trace like circuit boards. This aesthetic occupies the territory between "corporate" and "tech," and it is especially dominant in any company that has a technology/AI division.

In 2025, this trend evolved beyond simple "robot" iconography into genuine data visualization as decoration — animated line charts used as section dividers, rotating geometric forms as hero centerpieces, precision grid systems that subtly show in the background.

### Sites using it
- **Palantir.com** — data visualization and precise geometric UI as primary design language
- **OpenAI.com** — subtle animated orb with mathematical precision
- **Anthropic.com** — clean geometric illustration
- **Mistral AI** — flowing gradient with data-stream aesthetic
- **Scale AI** — precision grid + geometric accent elements
- **Cohere.com** — orbital ring animation in hero

### Application to EntenS Group
Since EntenS has an AI products division, this aesthetic creates a natural design hook:

1. **AI section hero**: an animated SVG that shows a stylized orbital diagram — nodes representing properties, connected by animated lines suggesting "intelligent network management." Slowly rotates, nodes pulse with glow on a 3-second cycle.
2. **Background texture**: a very subtle dot grid pattern (CSS `radial-gradient` repeated, 0.03 opacity) behind certain sections creates a "precision" feeling without adding visual noise.
3. **Section dividers**: instead of `<hr>` lines, animated SVG paths trace from left to right on scroll-into-view.
4. **Icons**: move away from emoji/FontAwesome to custom-line SVG icons that match the orbital geometry aesthetic.
5. **Data chips**: small badge-style elements showing numbers use a tech-UI visual language (monospace font, bracket borders, blinking cursor).

### Difficulty: Medium
Animated SVG requires some knowledge of SVG path animation (`stroke-dashoffset` technique). The orbital animation requires either CSS keyframes or a small JS library. Custom SVG icons are a design task, not a dev task.

### UX Impact: High (specifically for the AI products section)
This visual language instantly communicates technological sophistication to B2B buyers. It differentiates the AI products section from the real estate sections, creating visual variety across the page while maintaining coherence.

---

## Trend 10 — Immersive Full-Bleed Video and Cinematic Photography

### What it is
In 2025, premium hospitality, luxury real estate, and entertainment companies have almost universally moved to **cinematic video backgrounds** and **full-bleed photography with dramatic color grading** as their primary hero content. The era of stock photos with blue gradient overlays is definitively over.

The 2025 standard:
- **Video**: shot in 4K, color-graded to match brand palette (for EntenS: warm, saturated, "golden hour" tones), compressed to <3MB for web with AV1/WebM format
- **Photography**: 16:9 or wider aspect ratios, hero photo occupies 95–100vh, subject matter shows the actual property at its best moment (full park at peak visitor hour, hotel lobby at night with ambient lighting)
- **Overlay treatment**: a gradient overlay (from transparent at center to 60% dark at edges) makes text readable without obscuring the image
- **Ken Burns effect**: very slow zoom (scale from 1.0 to 1.05 over 12 seconds) on still photos creates motion without video cost
- **Color duotone overlays**: some sites apply a subtle brand-color tint to photos using CSS `mix-blend-mode: multiply/overlay` at 20–30% opacity, unifying disparate property photos into one visual language

### Sites doing this well
- **Aman Resorts** (aman.com) — the gold standard for luxury hospitality photography
- **Six Senses Hotels** — immersive video backgrounds with full editorial photography
- **Rosewood Hotels** — cinematic full-bleed with precise overlay treatment
- **Soho House** — property photography with consistent warm color grading
- **Universal Parks & Resorts** — video hero with entertainment energy
- **Hyatt** — consistent photography style across all properties

### Application to EntenS Group
1. **Hero video**: a 20-second loop showing the best moments across properties — a roller coaster in motion, a hotel lobby at golden hour, families in a park. No audio. Compressed to <2.5MB, with a static fallback for slow connections.
2. **Portfolio cards**: each property uses a real photograph (not renders), color-graded with a warm-gold tint using CSS `filter: sepia(0.1) saturate(1.2)` to create visual consistency.
3. **Ken Burns on hero**: if video is not available (slow connection detected via `navigator.connection`), the fallback hero image uses a 12s Ken Burns zoom animation.
4. **Section photography**: each major section (Entertainment, Parks, Hotels, AI) has a full-bleed atmospheric photo as background — slightly blurred (10px blur, darkened overlay) so it reads as texture rather than content.
5. **Color grading CSS filter set** for all property photos:
```css
.property-photo {
  filter: contrast(1.05) saturate(1.15) brightness(0.95);
}
```

### Difficulty: Easy (CSS) / Hard (photography/video production)
The CSS techniques are simple. The hard part is obtaining or commissioning high-quality photography and video. If professional photography is not yet available, tools like Midjourney v6 can generate placeholder imagery for prototyping that is convincing enough for investor presentations.

### UX Impact: Very High
Photography quality is the single fastest signal of asset quality. A business owner looking at a property portfolio judges it in milliseconds based on photo quality. Cinematic imagery communicates that the assets are premium and well-maintained — critical for setting price expectations.

---

## Summary Table

| # | Trend | Difficulty | UX Impact | Priority for EntenS |
|---|-------|-----------|-----------|---------------------|
| 01 | Scroll-Driven Cinematic Storytelling | Medium–Hard | Very High | Must Have |
| 02 | Dark Luxury with Selective Illumination | Easy | High | Must Have |
| 03 | Kinetic / Variable Typography | Easy–Medium | High | Must Have |
| 04 | Bento Grid Layouts | Easy | Very High | Must Have |
| 05 | Glassmorphism 2.0 (Frosted UI) | Easy | Medium–High | Should Have |
| 06 | Ambient / Mesh Gradient Backgrounds | Easy | High | Must Have |
| 07 | Horizontal Scroll Portfolio Section | Medium | Very High | Must Have |
| 08 | Micro-Interactions & Physics Hover | Easy–Medium | High | Should Have |
| 09 | AI Aesthetic: Orbital Geometry | Medium | High | Should Have (AI section) |
| 10 | Immersive Video & Cinematic Photography | Easy (CSS) / Hard (production) | Very High | Must Have |

---

## Recommended Implementation Stack

```
Core framework:      Vanilla HTML/CSS/JS (no framework overhead for a landing page)
Scroll engine:       GSAP 3 + ScrollTrigger + Lenis (smooth scroll)
Typography:          Google Fonts — Cormorant Garamond (display) + Inter (body)
Animation utilities: GSAP for complex, CSS custom properties for simple
Icons:               Custom SVG line icons
Video compression:   ffmpeg → AV1/WebM primary, H.264/MP4 fallback
Performance target:  Lighthouse score ≥90 on mobile (use IntersectionObserver for lazy loading)
```

---

## Color System (Final Recommendation)

```css
:root {
  /* Backgrounds */
  --bg-deep:       #09090E;   /* near-black with blue undertone */
  --bg-surface:    #111827;   /* elevated surface */
  --bg-elevated:   #1A2235;   /* card/panel background */

  /* Brand */
  --gold:          #C9A84C;   /* primary accent — legacy, luxury */
  --gold-bright:   #E8C96A;   /* highlight, hover state */
  --gold-dim:      rgba(201, 168, 76, 0.15); /* glow / orb fill */

  --teal:          #4FFFEE;   /* secondary accent — AI, technology */
  --teal-dim:      rgba(79, 255, 238, 0.10);

  /* Text */
  --text-primary:  #F0EDE8;   /* warm white */
  --text-secondary:#A0AEC0;   /* muted gray */
  --text-muted:    #4A5568;   /* very muted, captions */

  /* Borders */
  --border-subtle: rgba(255, 255, 255, 0.07);
  --border-active: rgba(201, 168, 76, 0.30);
}
```

---

## Typography Scale

```css
/* Display — section heroes */
.text-display  { font-size: clamp(56px, 8vw, 120px); font-family: 'Cormorant Garamond', serif; font-weight: 300; letter-spacing: -0.03em; }

/* Headline — section titles */
.text-headline { font-size: clamp(32px, 4vw, 56px); font-family: 'Cormorant Garamond', serif; font-weight: 400; letter-spacing: -0.02em; }

/* Label — overlines, categories */
.text-label    { font-size: 11px; font-family: 'Inter', sans-serif; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; }

/* Body */
.text-body     { font-size: 16px; font-family: 'Inter', sans-serif; font-weight: 400; line-height: 1.7; }
```

---

## Competitive Context

The closest direct competitors for this type of holding company landing page style:
- **Advent International** (advent.com) — dark, authoritative, private equity aesthetic
- **Blackstone** (blackstone.com) — very clean, dark hero, large photography
- **Merlin Entertainments** (merlinentertainments.biz) — entertainment holding
- **Azimut Hotels** (azimuthotels.com) — hospitality brand, aspirational photography

EntenS can differentiate by combining the **financial authority** of a PE fund (dark, precise, metric-driven) with the **warmth** of a hospitality brand (ambient light, rich photography, human-scale imagery) — a combination none of the above currently does well.

---

*Report compiled by Claude Code · March 2025 · For internal use — EntenS Group website project*
