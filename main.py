import os

# Specify the path as the parent directory (../)
directory_path = "../"

html_head = """
<!--build 1-->
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" href="favicon.png" type="image/png" />
    <link rel="stylesheet" type="text/css" href="styles.css" />
    <title>Media Mimic</title>
  </head>
  <body>
"""

html_foot = """
<script src="script.js"></script>
  </body>
</html>
"""

html_banner = """
    <img id="icon" src="favicon.png" />
    <h1>Media Mimic</h1>
    <p>Powered by a 16TB Hard Drive!</p>
"""

html_content = """
"""


def build_media_mimic():
    # Check if the parent directory exists
    if os.path.exists(directory_path) and os.path.isdir(directory_path):
        # Get a list of directories in the parent directory excluding certain directories
        directories = [d for d in os.listdir(directory_path) if os.path.isdir(os.path.join(directory_path, d)) and not d.startswith("_") and d not in ["$RECYCLE.BIN", "System Volume Information", "#media_mimic"]]

        # Print the list of directories
        for d in directories:
            html_content += f"{d}<br>\n"
            
    else:
        print("The parent directory is not valid.")

    return html_head + html_banner + html_content + html_foot


media_mimic_text = build_media_mimic()

#save media_mimic
media_mimic_file = open("index.html", "w")
media_mimic_file.write(media_mimic_text)
media_mimic_file.close()