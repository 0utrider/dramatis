# Dramatis

Character art and tokens for Foundry VTT, hosted for use in other GMs' games.

## Layout

```
<campaign>/<character>/
    character.yaml                  # metadata for everything below
    <character>-keyart[-NN].webp
    <character>-portrait.webp
    <character>-token[-NN].webp
    <character>-bust.webp           # optional
    companions/                     # familiars, pets, hires, eidolons
    summons/                        # summoned creatures, thralls
    fx/                             # art for spells, skills, abilities
```

Files are named `<subject>-<type>[-NN].webp`: lowercase ASCII and hyphens only. `-NN` is a two-digit
variant number, used only when more than one image of that type exists. Subfolder files use their own
subject name (`companions/obol-portrait.webp`, `fx/life-tap.webp`).

| Type | Spec | Purpose |
| --- | --- | --- |
| `keyart` | Any ratio, best-quality master | The definitive art piece |
| `portrait` | 1:1, closer crop | Foundry actor image |
| `token` | 1:1, 512×512, ringed, bust crop | Foundry canvas token |
| `bust` | Optional, head and shoulders, unringed | Source crop for tokens |
| `fx` | Any ratio | Spell, skill or ability art |

## Shared icons

`icons/<abilities|spells|equipment>/<subject>.webp` (512×512, no type suffix: the folder says it is an icon) are reusable icons not tied to one
character, listed in `icons/icons.yaml`. Example: `icons/abilities/thrall-strike-spirit.webp`, one per
damage type, for any necromancer's thrall attacks.

Every `.webp` carries embedded EXIF and XMP metadata (original repo URL, path, owner, license), written by
`scripts/manifest.py`, so a copied file can be traced back here.

`manifest.json` at the root lists every asset with its character fields. It is rebuilt and validated by
`scripts/manifest.py` on each commit (`cp scripts/pre-commit .git/hooks/pre-commit` to install the hook;
needs Python with Pillow and PyYAML).

## Using an image in Foundry

Paste the URL into an actor's image or token image field:

```
https://0utrider.github.io/dramatis/<path to file>
```

Example:

```
https://0utrider.github.io/dramatis/kingmaker/radomir/radomir-token.png
```

## Campaigns

- `kingmaker/`: Radomir and his retinue.
