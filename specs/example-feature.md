# Example spec: "Content" module, part 1 of 3

A real card the Maestro wrote and the `dev` agent executed (task #308), translated from
Portuguese. The only edits: the owner's internal business name and project identifiers were
removed. The structure is the point: objective, context the agent cannot know, numbered work,
explicit fences, and a proof of done that must be pasted, not claimed.

Outcome: delivered as one pull request, sent back once by the reviewer for missing items (UI,
uploads), fixed on the same PR, merged by the owner. The migration was applied by the Maestro
after the merge, as the spec requires.

---

# "Content" module (posting calendar) in the customer panel: part 1 of 3

## Objective
The owner will use the product itself as his own management panel, through an internal business
with no public page. The first module of that panel is a **posting calendar**: what will be
posted, when, where (Instagram, LinkedIn...), for which brand/product, on which theme, and at
which stage it is. It enters as a **new `content` module**, switched on manually in
`personalization.modules`, with its own tab in the panel (`MODULE_TABS` in
`src/app/account/account-panel.tsx`), exactly following the **Loyalty** module pattern. Use it as
the model: `supabase/migrations/0033b_loyalty_card.sql`, `src/app/api/account/loyalty/route.ts`,
`src/app/account/loyalty-tab.tsx`, `src/content/modules.ts`. Read `CLAUDE.md`/`AGENTS.md` (this
Next.js version has changes; read `node_modules/next/dist/docs/` before writing a route).

This is part 1 (data + calendar + post). Part 2 (idea bank, content pillars and cadence per
channel) and part 3 ("Generate draft" button for an agent, and a WhatsApp reminder) come later.
Do not build them now, but leave the model ready for them (columns below).

## ATTENTION: schema
Since 2026-11-03 the production database is the shared project, schema **`business`** (the app
sends `Accept-Profile: business`; see `src/lib/supabase-config.ts`). Older migrations in the repo
say `public.` because they were born in the old database. **The new migration must target the
`business` schema** (`set search_path = business`). Check real names in 0025 and 0033b (how
user access to the business and an enabled module are checked).

## What to do
1. **Migration `supabase/migrations/0043_content.sql`** (idempotent, `business` schema, same
   security style as 0033b: tables with RLS on and no policy, `revoke all ... from public, anon,
   authenticated`; everything through `security definer` functions with a fixed `search_path`,
   executable only by `service_role`; every function checks that `p_user` has access to business
   `p_number` and that the `content` module is enabled, before any read or write):
   - `content_channels` (id, business_id, name, type `instagram|linkedin|tiktok|youtube|whatsapp|other`,
     color, weekly_cadence int null [part 2], active, sort_order).
   - `content_brands` (id, business_id, name, color, active). Optional per post.
   - `content_posts` (id, business_id, channel_id, brand_id null, scheduled_at timestamptz null
     (null = no date, goes to the "No date" column), title text <=120, theme text <=80 null,
     format `post|carousel|reels|story|article|video|other`, status `idea|text|art|scheduled|published`
     (default `idea`), caption text <=5000, hashtags text <=500, published_link text null,
     published_at timestamptz null, notes text, created_at, updated_at). Index (business_id, scheduled_at).
   - `content_attachments` (id, post_id, business_id, storage path, name, mime type, size, order).
     Storage: reuse the bucket and route the panel already uses for images, under
     `content/<business>/<post>/`; max 10 files per post, images (png/jpg/webp) and pdf only, up to 10 MB each.
   - Functions: list for a period (channels, brands, posts in range + posts with no date),
     save post (create/edit; validates sizes and enums; `published` sets `published_at` if empty),
     delete post, move (drag in the calendar), save channel / brand, register/remove attachment.
   - Paste the full SQL in the report.
2. **Catalog**: in `src/content/modules.ts`, module `{ id: "content", name: "Content", groups: "*",
   status: "coming-soon" }` (NOT shown as available in the public offer; enabled only by hand).
   Make sure the tab appears when enabled even with status coming-soon.
3. **API** `src/app/api/account/content/route.ts` following the loyalty route pattern: GET (period)
   and POST with `action` = save-post | delete-post | move | save-channel | save-brand |
   attachment-register | attachment-remove. Size validation on the server too. Pure logic (week
   and month dates in Brasilia time, grouping by day, validation) in `src/lib/content.ts` with
   **vitest tests**.
4. **"Content" tab**, **mobile first (375px)**, and good at 1280px:
   - Top: toggle **Week | Month | List**, period arrows, "Today", filter by channel and brand.
   - **Week** (mobile: days stacked; desktop: 7 columns): each post is a card with the channel's
     color/icon, time, title, status chip. **Month**: grid with colored dots per channel; tapping a
     day opens it. **List**: upcoming posts in order + a "No date" block.
   - "+ Post" button (tapping an empty day creates with that date). Post sheet: channel, brand,
     date/time (or "no date"), title, theme, format, clickable status steps
     idea -> text -> art -> scheduled -> published, caption with counter, attachments (thumbnails,
     upload/remove), published link, notes, "Copy caption". Desktop: drag a card to another day.
   - Late = past date and status != published -> orange border.
   - First use with no channels: empty state offering one-tap suggestions (Instagram, LinkedIn).
   - Visually consistent with the current panel. No wide tables on mobile.
5. **Internal business with no public page**: it will be created directly in the database with
   `live = false`. Verify that a business with `live = false` does not appear on public pages,
   the sitemap, prospecting lists or reports. If some place does not filter it, do NOT change it
   now; just list where it appears in the report.

## Do NOT do
- Do NOT apply the migration in production: the Maestro applies it after the merge. File only.
- No real data in migrations, seeds or tests. Invented examples only.
- Do not touch scheduling, loyalty, sales funnel, WhatsApp or billing. Do not post anything to a
  social network (there is no integration in this part).
- A component written only for the screenshot that imitates a screen does NOT count as a
  screenshot. If the real screen does not render, say what was missing.

## Proof of done
- `npx tsc --noEmit`, `npx vitest run`, `npm run lint` and `npm run build` green (paste the real
  end of the output, not a summary).
- REAL screenshots of the Content tab at 375px (Week, Month, List, open post sheet) and at 1280px
  (Week), with invented data. Commit the PNGs under `docs/screenshots/content/` in the PR.
- The 0043 SQL pasted in the report.
- Branch `feat/mc-content`, PR to main, PR URL and preview URL. The final report becomes the
  task comment automatically: do not try to comment on a GitHub issue.
