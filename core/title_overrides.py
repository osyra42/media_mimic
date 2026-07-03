"""Folder-name -> OMDb query overrides.

Only titles whose correct OMDb name contains a character Windows forbids in a
folder name (mainly ':') live here - those can't be fixed by renaming the
folder. Everything else was resolved by renaming the folder to match OMDb.

Keys match the RAW folder name (case-insensitive-exact). Add an entry when a
title comes back as "no data" and its correct name needs an illegal char.
"""

OVERRIDES = {
    "DnD Wrath of the Dragon God": "Dungeons & Dragons: Wrath of the Dragon God",
    "Dungeons and Dragons Honor Among Thieves":
        "Dungeons & Dragons: Honor Among Thieves",
    "Final Fantasy 7 Complete": "Final Fantasy VII: Advent Children",
    "Frieren Beyond Journeys End": "Frieren: Beyond Journey's End",
    "Full Metal Alchemist Brotherhood": "Fullmetal Alchemist: Brotherhood",
    "Law and Order SVU": "Law & Order: Special Victims Unit",
    "Spiderman Spider-Verse": "Spider-Man: Into the Spider-Verse",
    "The Croods A New Age": "The Croods: A New Age",
}
