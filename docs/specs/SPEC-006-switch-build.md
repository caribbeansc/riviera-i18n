# SPEC-006: Switch build, installation and packaging

`python rpl.py switch build <lang>` turns a language pack and the user's dump into a LayeredFS mod:

```
<out>/exefs/<build id>.ips          the patch for `main` (the name Eden, yuzu and their forks look for)
<out>/exefs/<first 16 bytes>.ips    the same patch under the name Ryujinx and Atmosphère look for
<out>/romfs/data.bin                the font atlas with the accented letters
<out>/romfs/data_en.bin             the translated pictures
<out>/report.json                   what did not fit, what has no glyph, the verification result
```

## Requirements

- **R-1** A build writes the two IPS names, both containers and the report.
- **R-2** The two IPS files hold the same patch; the short name is 32 hex digits.
- **R-3** Applying the patch to `main` gives an executable whose script is the translation (markers kept, voice tags kept), and
  whose Japanese, Korean and Chinese rows are untouched.
- **R-4** `data.bin` carries the atlas extended to 43 rows and every other file unchanged; `data_en.bin` carries the translated
  pictures and every other file unchanged.
- **R-5** The build is reproducible: building twice gives the same bytes.
- **R-6** `with_romfs=False` writes only the patch.
- **R-7** A build the toolkit does not know, a missing dump and a pack without a script are refused with a message that says what to do.
- **R-8** A picture whose original is not the one the translation was made against is reported as a warning.
- **R-9** Installing copies the mod into `<mods folder>/<mod name>/{exefs,romfs}`, replacing an earlier copy, and refuses something
  that is not a built mod; removing deletes only that folder.
- **R-10** Emulator mod folders are found per family: Ryujinx and forks use a lowercase title id under `mods/contents`, yuzu, Eden
  and forks an uppercase one under `load`; folders that do not exist are not offered.
- **R-11** The Atmosphère package puts the patch in `atmosphere/exefs_patches/<mod>/<first 16 bytes>.ips` and the containers in
  `atmosphere/contents/<title id>/romfs/`.
- **R-12** Installing on an Android device goes over adb to the emulator's `files/load/<title id>/<mod>/` folder, pushing each file,
  and refuses while the emulator is running.
- **R-13** Against a real v1.0.0 dump, the Spanish mod builds with no row left without room, no verification failure and no overflow,
  the checksum of its patch is the pinned one, and every key of the pack that the game has passes the validator.
