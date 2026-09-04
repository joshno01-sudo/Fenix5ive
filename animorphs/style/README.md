# Animorphs fan adaptation — animation style boards

Style research and approval renders for the fan-made animated adaptation of
K. A. Applegate's *Animorphs*. The brief: move away from the earlier cartoon
styling toward the look of *Batman: The Animated Series* / *Superman: The
Animated Series* (the Bruce Timm "Timm style") or *Young Justice* (Phil
Bourassa's designs).

Round one drew both treatments side by side. The direction after review is
Timm's style as closely as we can mirror it, so round two rebuilds the
characters on his construction: three-quarter heads, lantern jaw and squared
chin on the boys, heart face and pointed chin on the girls, small eyes with
dot pupils under wedge brows, one thin uniform outline, flat colour with no
face shading. The kids appear as heads and as a full-figure lineup, plus a
first-episode scene, an alien model sheet and a title card.

## Files

| File | What it is |
| --- | --- |
| `renders/01-heads.png` | Jake, Rachel, Marco, Cassie, Tobias, Ax — three-quarter heads on Timm construction |
| `renders/02-figures.png` | The same six as a full-figure lineup against a head-count scale |
| `renders/03-scene-construction-site.png` | Episode one scene study: the abandoned construction site, Elfangor's fighter |
| `renders/04-aliens-model-sheet.png` | Andalite (Ax) and a Hork-Bajir Controller against a height bar |
| `renders/05-title-card.png` | "The Invasion, Part One" title card in the DCAU black-card convention |
| `renders/*.svg` | Vector masters of the above, fonts embedded |
| `render_styleboards.py` | Rebuilds every SVG from scratch (Python 3 only, no packages) |
| `rasterize.sh` | Screenshots the SVGs to 3200×1800 PNGs with the bundled Chromium |
| `review.html` | The side-by-side review page (published as an Artifact) |

```bash
python3 render_styleboards.py   # writes renders/*.svg
./rasterize.sh                  # writes renders/*.png (needs chromium; PIL optional, for the crop)
```

## What the research says

### Timm style (Batman: TAS 1992, Superman: TAS 1996, "Batman & Superman Adventures")

- **Streamlined and angular.** Body shapes are drawn with long unbroken lines
  and as little sculpting as possible, which makes figures read as angular.
  Faces have an angular structure and a squared, "lantern" jaw on the men.
- **Small eyes, minimal facial detail.** This is what keeps it from feeling
  cartoony. Eyes are small with a heavy straight upper lid; the nose is one
  stroke; the mouth is one line.
- **Simple hair.** A hairstyle is one solid silhouette with a few sharp
  points, plus one highlight shape.
- **Flat colour, few colours.** Costumes use a handful of flat colours, one
  cel shadow tone and no texture, which is what makes the style cheap and
  consistent to animate.
- **Dark Deco.** The producers' own term for the blend of film-noir mood and
  1930s–40s Art Deco architecture. Eric Radomski had all backgrounds painted
  with light colours on black paper rather than dark colours on white, which
  gives the series its depth and its "one colour of light" feel.
- **Proportions** are fairly realistic but exaggerated — heroic upper body
  mass, slim legs. The show favours strong, held poses.
- Superman: TAS pushed the design even more streamlined and consistent than
  Batman, and darkened its palette to feel more like the comics.

### Young Justice (2010–, designs by Phil Bourassa)

- **Grounded realism.** Producer Brandon Vietti insisted the visuals be
  "grounded in a believable and realistic-feeling world", with fantasy
  elements arriving sparingly for impact. Bourassa's rule: the look, feel and
  tone of the design has to suit the story and the world.
- **Realistic teen proportions** and softer, more naturalistic faces than
  Timm's: irises, eye highlights, defined noses and lips, individual hair
  strands.
- **More detail, still animatable.** Bourassa's position is that "as long as
  the theory and mechanics of the designs are sound, the animators can handle
  anything" — detail is fine when it isn't superfluous. In practice that means
  two shading tones plus a highlight plane, seams and folds on clothing,
  layered real-world outfits.
- **Comic-book lineage.** Bourassa came from comics and treats each character
  as "a thoughtful and respectful update of a classic" rather than a
  redesign for its own sake.

## Timm construction, as used in the boards

- **Three-quarter view.** The face is turned so the nose breaks the far-side
  silhouette as one straight bridge line to a sharp tip. The near jaw is a
  straight diagonal from under the ear to the chin.
- **Boys:** broad squared chin, thick neck as wide as the jaw, wedge brows
  sitting almost on the lid, small eye whites with a dot pupil, one-line
  mouth with a chin crease. **Girls:** heart-shaped face to a small pointed
  chin, larger eyes with a heavy lid and a lash flick, thin arched brows, a
  small upturned nose, full painted lips.
- **Hair** is one solid silhouette with sharp points and one highlight shape.
- **One thin uniform black outline, flat colour, no shading on the face.** The
  single shadow kept is under the jaw on the neck.
- **Bodies:** broad shoulders tapering to the waist, thighs tapering to the
  knee, blocky hands. Heights are teen heights, Jake at 7 heads down to
  Marco at 6, rather than Timm's 8-head adults.

## The two treatments as drawing rules (round one research)

| | Dark Deco (Timm) | Grounded (Bourassa) |
| --- | --- | --- |
| Outline | Unbroken, angular, uniform ~3 px black line | Finer ~2 px dark-brown line, softer curves |
| Head | Squared jaw (men), pointed chin (women), small features | Realistic teen skull, softer jaw |
| Eyes | Small whites, black pupil dot, heavy upper lid | Almond eyes with iris colour, pupil, one highlight, lash flick |
| Nose / mouth | One stroke each | Bridge + nostrils; lip line + lower-lip shadow |
| Hair | One solid silhouette + one highlight shape | Silhouette + strand lines + two-tone |
| Shading | Flat colour + one cel shadow | Shadow + highlight plane, cloth folds |
| Clothing | One garment, 2–3 colours | Layered outfits, seams, hardware |
| Backgrounds | Light painted onto black, deco geometry, one colour of light | Painted gradients, believable suburban horizon |
| Animation cost | Low: fewest lines, fewest colours | Higher: more line, more tones per cel |

## Direction

**Dark Deco (Timm), mirrored as closely as we can, with the kids kept at
teen proportions.** Animorphs is
a story about ordinary thirteen-year-olds hiding a war in a suburb, and its
horror is in what the morphs do to bodies. Timm's discipline suits that: the
flat, quiet human world makes the morph sequences and the aliens land harder,
the night-time light-on-black backgrounds give us the construction site, the
Yeerk pool and the mall basement for free, and the uniform line keeps a fan
production consistent across episodes. What we borrow from *Young Justice* is
the proportion and the grounding — no heroic upper bodies on the kids, real
clothes, a believable town — so it reads as teens, not as junior superheroes.

The Grounded (Young Justice) treatment from round one was dropped at review;
its research stays above for reference.

## Character notes used in the boards

- **Jake** — tall, brown hair and eyes, plain tee. Reluctant leader.
- **Rachel** — tall, blonde, "flawless complexion"; dresses well (fitted top,
  denim jacket). Jake's cousin.
- **Marco** — dark, longer hair in the early books, olive skin, hoodie. The
  wise guy.
- **Cassie** — Black, short cropped hair, barn clothes (overalls over a tee).
  Works at her parents' wildlife rehabilitation clinic.
- **Tobias** — dirty blond, shaggy, worn flannel. The outsider.
- **Ax** — human morph blended from the other four: light-brown-sugar skin,
  brown hair with a little of Rachel's gold and Marco's curl.
- **Andalite** — blue-and-tan centauroid, deer-like lower body with four
  hooves, weak arms with many-fingered hands, no mouth, two main eyes and two
  stalk eyes, a tail ending in a scythe blade. Blue blood.
- **Hork-Bajir** — seven feet, green-black leathery hide, snake neck, beak,
  tyrannosaur feet, blades at head, elbows, wrists, knees, feet and tail.

## Sources

- TV Tropes, "Timm Style" — https://tvtropes.org/pmwiki/pmwiki.php/Main/TimmStyle
- Character Design References, "Art of Batman: The Animated Series" — https://characterdesignreferences.com/art-of-animation-4/art-of-batman-the-animated-series
- Illustration History, "Bruce Timm" — https://www.illustrationhistory.org/artists/bruce-timm
- DCAU Wiki, "Revamp" (Superman: TAS design changes) — https://dcau.fandom.com/wiki/Revamp
- The World's Finest, "Young Justice — Interview with Phil Bourassa" — https://dcanimated.com/young-justice/extras/young-justice-interview-with-phil-bourassa-1/
- Young Justice Wiki, "Phil Bourassa" — https://youngjustice.fandom.com/wiki/Phil_Bourassa
- Seerowpedia (Animorphs wiki), character and species pages — https://animorphs.fandom.com/
- Hirac Delest, Animorphs character database — https://www.hiracdelest.com/database/characters/jake.htm
