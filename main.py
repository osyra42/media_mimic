import os
import time

process_start = time.time()
# Open the file in read mode
with open("build.txt", "r") as build_file:
    # Read the content and convert it to an integer
    build_text = int(build_file.read().strip())
    # Increment the value by 1
    build_text += 1

# Open the file again in write mode
with open("build.txt", "w") as build_file:
    # Write the updated value (converted to string) to the file
    build_file.write(str(build_text))


# Specify the path as the parent directory (../)
directory_path = "../"


def build_media_mimic():
    html_head = f"""<!--build {build_text}-->
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
    <div id="header"> 
        <img id="icon" src="favicon.png" />
        <h1>Media Mimic</h1>
        <p>Powered by a 16TB Hard Drive!</p>
    </div>
    """

    html_content = """
"""

    # Check if the parent directory exists
    if os.path.exists(directory_path) and os.path.isdir(directory_path):
        # Get a list of directories in the parent directory excluding certain directories
        directories = [d for d in os.listdir(directory_path) if os.path.isdir(os.path.join(directory_path, d)) and not d.startswith("_") and d not in ["$RECYCLE.BIN", "System Volume Information", "#media_mimic"]]

        # Print the list of directories
        html_content += """<div id="content">\n"""
        for category in directories:
            print(f"Searching the category {category} . . .")
            time.sleep(0.0)

            html_content += f"""  <div class="ribbon">{category}</div>\n"""
            series = [d for d in os.listdir(f"{directory_path}/{category}") if os.path.isdir(os.path.join(f"{directory_path}/{category}", d)) and not d.startswith("_")]
            html_content += "  <div>\n"
            for title in series:
                print(f"    Found {title}!")
                time.sleep(0.0)

                html_content += f"""    <div class="tile">
      <p>{title}</p>
      <img src="thumbnails/{title}.jpg">\n    </div>\n"""
            html_content += "  </div>\n"


        html_content += "</div>\n"
            
    else:
        print("The parent directory is not valid.")

    return html_head + html_banner + html_content + html_foot


media_mimic_text = build_media_mimic()

#save media_mimic
media_mimic_file = open("index.html", "w")
media_mimic_file.write(media_mimic_text)
media_mimic_file.close()

process_end = time.time()
process_time = round(process_end - process_start, 2)
print(f"DONE in {process_time} seconds")