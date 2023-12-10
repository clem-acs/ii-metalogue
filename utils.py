def text_wrap(text, line_length):
    lines = []
    words = text.split(' ')
    line = ''
    for word in words:
        # If the word itself is longer than the line length, split it
        while len(word) > line_length:
            if line:  # If there's already a line, add it to the lines list
                lines.append(line)
                line = ''
            lines.append(word[:line_length])  # Add the first part of the word to the lines list
            word = word[line_length:]  # Keep the rest of the word for the next line
        # If adding the next word would exceed the line length, start a new line
        if len(line) + len(word) + 1 > line_length:
            lines.append(line)
            line = word
        else:
            line += (' ' + word if line else word)  # Add a space if not the first word in the line
    lines.append(line)
    return lines