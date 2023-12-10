from blessed import Terminal
from itertools import zip_longest
from utils import text_wrap
import argparse
import time
import pickle
import csv

# TODO:
# maybe some key to add a sibling to the current node (it would be especially nice in conjunction with the point above)
# probably with that visualizing siblings approach, it would be handy to edit nodes (so that you can update the top nodes which serve as a preview)

parser = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description="""\
World's first rotodendron

controls:
- typing when there's a cursor
- enter to submit a para / create branch in reading mode
- tab to switch to reading mode and go to the top / go to next para in reading mode
- arrow keys for moving cursor in writing mode / navigating branches in reading mode
- hjkl to move between paragraphs in reading mode
- esc to to switch to reading mode
"""
)
parser.add_argument("--autoloop", action=argparse.BooleanOptionalAction, default=True, help="Whether to loop around automatically")
parser.add_argument("-f", "--file", type=str, default="tree", help="File name (without extension) to load from and save to. Will create a pickle file with the full state saved, and also a markdown file with the exported tree.")
args = parser.parse_args()
if args.autoloop:
    autoscroll_delay = 0.65                                                  
    initial_timer = 20
else:
    autoscroll_delay = None
    initial_timer = 100


class Node:
    node_id = 0 # shared class variable

    def __init__(self, text, parent=None):
        self.text = text
        self.children = []
        self.parent = parent
        self.creation_time = time.time()
        self.id = Node.node_id
        Node.node_id += 1

        self.parent_id = parent.id if parent else None

    def add_child(self, node):
        self.children.append(node)

class Tree:
    def __init__(self):
        self.root = Node("")
        self.current_stream = []

    def node_at_index(self, index):
        node = self.root
        for i in range(index):
            node = node.children[self.current_stream[i]]
        return node

    def grow(self, text, index):
        selected_node = self.node_at_index(index)

        self.current_stream = self.current_stream[:index]
        self.current_stream += [len(selected_node.children)]

        new_node = Node(text, parent=selected_node)
        selected_node.add_child(new_node)

    def switch_stream(self, index, increment, leaf_explore = False):
        """
        Switches stream to a sibling node of the node at index, in the direction of the incrememnt. 

        If current node has no siblings in direction of increment, it will try to find siblings upstream.
            - choosing either the leftmost or right most branches downstream, depending on increment.

        If "leaf_explore" is set to true, then it also descends to the leaf, which lets you scroll thorugh all streams.
            - at the moment, this is set true if this is called on a leaf node
            - it might make more sense to introduce a different control for this, as might be unwanted beahvior sometimes

        If the tree terminates before it descends to current index, it returns the index corresponding to the leaf. 
        """
        if index is len(self.current_stream):
            leaf_explore = True
        original_index = index
        while index > 1:
            parent = self.node_at_index(index-1)
            new_stream_at_index = self.current_stream[index-1] + increment
            if new_stream_at_index >= 0 and new_stream_at_index < len(parent.children):
                self.current_stream = self.current_stream[:index-1] + [new_stream_at_index]
                node = parent.children[new_stream_at_index]
                while node.children:
                    if increment >= 0:
                        self.current_stream += [0]
                        node = node.children[0]
                    else:
                        self.current_stream += [len(node.children)-1]
                        node = node.children[-1]
                    if leaf_explore:
                        index += 1
                return index
            # there were no siblings at current depth, so move up
            index -= 1
        # we failed to find a sibling, so do nothing
        return original_index

    def get_stream(self):
        stream = []
        node = self.root
        for step in self.current_stream:
            n = len(node.children)
            node = node.children[step]
            stream.append({
                "text": node.text,
                "num_before": step,
                "num_after": n - step - 1
            })
        return stream
    
    def get_stream_with_siblings(self):
        stream = []
        node = self.root
        for step in self.current_stream:
            stream.append({
                "texts": [s.text for s in node.children],
                "nodes_to_left": step,
            })
            node = node.children[step]
        return stream
    
    def print_tree(self, file_handle, node=None, prefix=""):
        if node is None:
            # here we assume that the root is empty and irrelevant and it has only one child
            node = self.root.children[0]
        
        # print(prefix + "- " + node.text)
        file_handle.write(prefix + "- " + node.text + "\n")
        prefix += "\t"
        for child in node.children:
            self.print_tree(file_handle, child, prefix=prefix)
    
    def collect_node_data(self, node, parent_text, data, depth=0):
        """
        Recursive function to collect node data.
    
        Arguments:
        - node: Current node.
        - parent_text: Text attribute of the parent node
        - data: List to store the data of all nodes.
        - depth: Depth of the current node in the tree.
        """
        data.append({
            'node_text': node.text,
            'parent_text': parent_text,
            'creation_time': node.creation_time,
            'depth': depth,
            'node_id': node.id,
            'parent_id': node.parent_id
        })
    
        for child in node.children:
            self.collect_node_data(child, node.text, data, depth + 1)

    def export_tree_to_csv(self, filename):
        """
        Function to export a tree to a CSV file.
    
        Arguments:
        - tree: The tree to export.
        - filename: The name of the CSV file to create.
        """
        data = []
        self.collect_node_data(self.root, '', data)
    
        with open(filename, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['node_text', 'parent_text', 'creation_time', 'depth', 'node_id', 'parent_id'])
            writer.writeheader()
            writer.writerows(data)

class Editor:
    def __init__(self, term):
        self.term = term
        self.tree = Tree()
        self.reading_mode = False
        self.selected_index = 0

        # for reading mode
        self.line_in_para = 0

        # for writing mode
        self.current_text = ""
        self.cursor_position = 0
        
        # formatting
        self.column_width = 35
        self.gap_width = 5

        self.highlight = lambda x: x
        self.unhighlight = term.color(8)
        self.cursor_style = lambda x: term.on_white(term.black(x))

        # buffer for smooth display
        self.last_display = []

        # timing for catch up
        self.current_timer = initial_timer

        # shuttle
        self.shuttle = []
        self.show_shuttle = True

    def generate_display(self):
        current_text = self.current_text[:self.cursor_position] + "⎸" + self.current_text[self.cursor_position:]
        current_text_wrapped = text_wrap(current_text, self.column_width)
        pad_left = (self.term.width - self.column_width) // 2
        full_col_width = self.column_width + self.gap_width

        rows = []
        scroll_index = 0

        stream = self.tree.get_stream_with_siblings()

        if not stream:
            rows = [" " * pad_left + self.highlight(line) for line in current_text_wrapped]
            scroll_index = len(rows)

        def format_row(column_texts, nodes_to_left):
            formatted_texts = [text_wrap(text, self.column_width) for text in column_texts]
            max_height = max(len(lines) for lines in formatted_texts) if formatted_texts else 0
            for line_num in range(max_height):
                full_line = ""
                for column_lines in formatted_texts:
                    chunk = column_lines[line_num] if line_num < len(column_lines) else ""
                    full_line += f"{chunk:<{full_col_width}}"
                # center the line
                full_line = " " * pad_left + full_line
                # shift it left
                full_line = full_line[nodes_to_left * full_col_width:] 
                # cut off the right
                full_line = full_line[:self.term.width]
                yield full_line
                
        for i, item in enumerate(stream):
            is_selected = i+1 is self.selected_index

            format_ = self.highlight if is_selected and self.reading_mode else self.unhighlight
            for line in format_row(item["texts"], item["nodes_to_left"]):
                rows.append(format_(line))

            if is_selected and self.reading_mode:
                scroll_index = len(rows) # set scroll view to here

            # add current text in writing mode
            if is_selected and not self.reading_mode:
                rows.append("")
                # get sibling nodes
                siblings = [node.text for node in self.tree.node_at_index(self.selected_index).children]
                # add current text
                for line in format_row(siblings + [current_text], len(siblings)):
                    rows.append(self.highlight(line))

                scroll_index = len(rows) # set scroll view to here
                rows += [""] * self.current_timer
            
            rows.append("")

        # TODO: scrolling rows
        if self.selected_index is len(stream) and not self.reading_mode:
            stream = self.tree.get_stream()
            for item in stream:
                lines = text_wrap(item["text"], self.column_width)
                format = self.unhighlight
                rows.append(
                    " " * (pad_left - (1 + item["num_before"]))
                    + format("<" * item["num_before"]) + " "
                    + format(lines[0]) + " " * (self.column_width - len(lines[0]))
                    + " " + format(">" * item["num_after"])
                )
                rows.extend([" " * pad_left + format(line) for line in lines[1:]])
                rows.append("")

        # scrolling 
        middle_height = self.term.height // 2
        scroll_index += middle_height
        rows = [""] * middle_height + rows

        start_index = scroll_index - middle_height
        end_index = scroll_index + self.term.height
        
        ret = rows[start_index:end_index]

        return ret
    
    def update_display(self):
        with self.term.hidden_cursor():
            new_display = self.generate_display()

            # update difference
            for i, (old_line, new_line) in enumerate(zip_longest(self.last_display, new_display, fillvalue="")):
                if old_line != new_line:
                    with self.term.location(0, i):
                        print(self.term.clear_eol, end="")
                        print(new_line, end="")
            for i in range(len(new_display), len(self.last_display)):
                with self.term.location(0, i):
                    print(self.term.clear_eol, end="")

            self.last_display = new_display

    def lines_in_current_para(self):
        return 1 + len(text_wrap(self.tree.get_stream()[self.selected_index-1]["text"], self.column_width))
        # # rewrite to not use get_stream
        # return 1 + len(text_wrap(self.tree.node_at_index(self.selected_index).text, self.column_width))
        # # if that works correctly, we can get rid of get_stream

    def set_reading_mode(self):
        self.reading_mode = True
        self.line_in_para = 0
        self.current_text = ""
        self.cursor_position = 0
        self.selected_index += 1
        if self.selected_index > len(self.tree.current_stream):
            self.tree.switch_stream(self.selected_index-1, 1, True) # added this for the metalogue
            self.selected_index = 1
        self.current_timer = initial_timer

    def prev_line(self):
        if self.reading_mode:
            self.line_in_para -= 1
            if self.line_in_para == -1:
                if self.selected_index == 1:
                    self.line_in_para = 0
                else:
                    self.selected_index -= 1
                    self.line_in_para = self.lines_in_current_para() - 1
        else:
            self.reading_mode = True
            self.line_in_para = self.lines_in_current_para() - 1


    def next_line(self):
        if self.reading_mode:
            self.line_in_para += 1
            if self.line_in_para >= self.lines_in_current_para():
                self.next_para()
        else:
            self.current_timer -= 1
            if self.current_timer == 0:
                self.set_reading_mode()

    def next_para(self, keep_in_reading_mode=False):
        self.line_in_para = 0
        if self.selected_index is len(self.tree.current_stream):
            if keep_in_reading_mode:
                return
            self.reading_mode = False
        else:
            self.selected_index += 1

    def prev_para(self):
        self.line_in_para = 0
        if self.selected_index > 1:
            self.selected_index -= 1

    def submit_para(self):
        self.tree.grow(self.current_text, self.selected_index)
        self.selected_index += 1
        self.current_text = ""
        self.cursor_position = 0
        self.current_timer = initial_timer

    def handle_keypress(self, key):
        if key.is_sequence:
            if key.name == "KEY_ENTER":
                if self.reading_mode:
                    self.reading_mode = False
                elif self.current_text:
                    self.submit_para()
                elif self.selected_index < len(self.tree.current_stream):
                    self.set_reading_mode()
            elif key.name == "KEY_TAB":
                if self.reading_mode:
                    self.next_para()
                elif self.tree.current_stream:
                    # Curious @filip: I don't like this feature: I want to delete para on TAB. whatcha think?
                    # if self.current_text:
                    #    self.submit_para()
                    self.set_reading_mode()
            elif key.name == "KEY_BACKSPACE" and self.current_text and not self.reading_mode:
                self.current_text = self.current_text[:self.cursor_position-1] + self.current_text[self.cursor_position:]
                self.cursor_position = max(0, self.cursor_position-1)
            elif key.name == "KEY_RIGHT":
                if self.reading_mode:
                    self.selected_index = self.tree.switch_stream(self.selected_index, 1)
                else:
                    self.cursor_position = min(len(self.current_text), self.cursor_position+1)
            elif key.name == "KEY_LEFT":
                if self.reading_mode:
                    self.selected_index = self.tree.switch_stream(self.selected_index, -1)
                else:
                    self.cursor_position = max(0, self.cursor_position-1)
            elif key.name == "KEY_DOWN":
                self.next_line()
            elif key.name == "KEY_UP":
                self.prev_line()
            elif key.name == "KEY_ESCAPE":
                if not self.reading_mode:
                    if self.current_text:
                        self.submit_para()
                    for _ in range(1 + len(text_wrap(self.current_text, self.column_width))):
                        self.prev_line()

        else:
            if key:
                if self.reading_mode:
                    if key == "j" or key == "n":
                        self.next_para(keep_in_reading_mode=True)
                    elif key == "k" or key == "e":
                        self.prev_para()
                    elif key == "h" or key == "m":
                        self.selected_index = self.tree.switch_stream(self.selected_index, -1)
                    elif key == "l" or key == "i":
                        self.selected_index = self.tree.switch_stream(self.selected_index, 1)
                    elif key == "p": #shuttle
                        self.shuttle.append(self.tree.get_stream()[self.selected_index-1]["text"])
                if not self.reading_mode:
                    self.current_text = self.current_text[:self.cursor_position] + key + self.current_text[self.cursor_position:]
                    self.cursor_position += 1
            else: #timer event
                self.next_line()
    
term = Terminal()
editor = Editor(term)

# load tree from pickle
try:
    with open(args.file + ".pickle", "rb") as f:
        editor.tree = pickle.load(f)
        editor.tree.current_stream = []
        node = editor.tree.root
        while node.children:
            editor.tree.current_stream += [0]
            node = node.children[0]
        #editor.selected_index = len(editor.tree.current_stream)
except FileNotFoundError:
    pass

print(term.clear)
with term.cbreak():
    while True:
        try:
            editor.update_display()
            key = term.inkey(timeout=autoscroll_delay)
            editor.handle_keypress(key)
        except KeyboardInterrupt:
            # if there's a current text, submit it
            if editor.current_text:
                editor.submit_para()
            # save the tree as markdown
            with open(args.file + ".md", "w") as f:
                editor.tree.print_tree(f)
            # pickle the tree
            with open(args.file + ".pickle", "wb") as f:
                pickle.dump(editor.tree, f)
            # save nodes as csv
            editor.tree.export_tree_to_csv(args.file + ".csv")
            break
