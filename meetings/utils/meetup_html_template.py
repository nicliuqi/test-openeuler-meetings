def cover_content(topic):
    content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>cover</title>
    </head>
    <body>
        <div style="display: inline-block; height: 688px; width: 1024px; text-align: center; background-image: url('meetup.png')">
            <p style="font-size: 80px; margin-top: 380px; color: white">{}</p>
        </div>
    </body>
    </html>
    """.format(topic)
    return content
