from tree_sitter import Language, Parser

colors = {
    0: "style:{ stroke:'#AE4946', fill:'white', lineWidth: 3 },\n", 
    1: "style:{ stroke:'#6082B6', fill:'white', lineWidth: 2.5 },\n", 
    2: "style:{ stroke:'#76A95A', fill:'white', lineWidth: 2 },\n",
    3: "style:{ stroke:'black', fill:'white' },\n",
}

class parser:
    def __init__(self) -> None:
        Language.build_library(
            'build/my-languages.so',
            [
                './tree-sitter-java'
            ]
        )
        JAVA_LANGUAGE  = Language('build/my-languages.so', 'java')
        self.parser = Parser()
        self.parser.set_language(JAVA_LANGUAGE)
        
    # 返回分析树
    def parse(self, filepath="./Input.java"):
        with open(filepath, "r") as f:
            code = f.read()
        code = "class CLASSNAME {\n" + code + "\n}"
        return self.parser.parse(bytes(code, "utf-8"))

# 使用哪个域作为label
def if_use_text(node):
    return 'identifier' in node.type or "literal" in node.type

# 获取结点的名字
def get_node_name(node):
    if if_use_text(node):
        return bytes.decode(node.text)
    else:
        return change_name_style(node.type)

# 把下划线命名改成大驼峰命名
def change_name_style(name:str):
    if '"' in name:
        return name
    name = "_" + name
    while '_' in name:
        pos = name.find('_')
        new_name = name[:pos] + name[pos+1].upper() + name[pos+2:]
        name = new_name
    return name

# 获取所有的简单路径到ans中
def get_paths(node, path, ans, tag="text"):
    if not short_identifier_check(node):
        return
    
    # 现在结点可以加入
    path_copy = path[:]
    if tag == "text":
        path_copy.append(get_node_name(node))
    elif tag == "index":
        path_copy.append(node.parent.children.index(node))

    # 查看是否继续递归
    if (len(node.children)) and not leaf_check(node):
        for child in node.children:
            get_paths(child, path_copy, ans, tag)
    else:
        ans.append(path_copy)
        return

# 检查是否是叶子
def leaf_check(node):
    if len(node.children) == 0:
        return True # 没有孩子，是叶子
    else:
        for child in node.children:
            if short_identifier_check(child):
                return False # 有一个孩子有效，不是叶子
        return True # 孩子全都无效，是叶子

# 找到method_declaration结点
def find_method_declaration_node(root):
    return root.children[0].children[2].children[1]

# 检测是否是很短的非标识符
def short_identifier_check(node):
    name = str(node.type)
    name = name.replace("_", "")
    return name.isalnum()

# 给一棵树加标记
def add_label_on_tree(method_node, path, tag:int, tree_dict):
    """
    tag: 第几大Attention，一般是3，2，1（1最大）
    tree_dict: 树的词典，给定node，返回其Attention程度标记
    """
    iterator = method_node
    tree_dict[iterator.id] = tag

    footprint = path[1:] # 第一个就是现在的iterator，所以忽略
    for foot in footprint:
        iterator = iterator.children[foot]
        tree_dict[iterator.id] = tag

# DFS生成JSON代码
json = ""
def gen_json(node,depth,rank_dict):
    global json
    # 过短的type可能是;等，不接受
    if not short_identifier_check(node):
        return

    json += f"{depth*'    '}"
    json += "{\n"
    json += f"{(depth+1)*'    '}"
    json += f"label:'{get_node_name(node)}',\n"
    # 添加标记信息
    json += f"{(depth+1)*'    '}"
    if node.id in rank_dict:
        if rank_dict[node.id] in colors:
            json += colors[rank_dict[node.id]]
    else:
        json += colors[3]


    if (len(node.children)) and not leaf_check(node):
        json += f"{(depth+1)*'    '}"
        json += (f"children:[\n")
        for child in node.children:
            gen_json(child, depth+1, rank_dict)
        json += f"{(depth+1)*'    '}"
        json += ("],\n")
    else:
        json += f"{(depth+1)*'    '}"
        json += (f"type:'rect',\n")

    json += f"{depth*'    '}"
    json += ("},\n")

# 读取模型生成的路径，正反各一条，用的时候索引*2和*2+1即可
def read_model_paths():
    with open("./model_output_path.txt", "r") as f:
        origin = f.read().split('\n')
    ans = []
    for line in origin:
        rever = "".join(reversed(line))
        last_up = len(rever) - rever.find("^") - 1
        ans.append(line[:last_up])
        first_down = line.find("_") + 1
        ans.append(line[first_down:])
    return ans

import Levenshtein

if __name__ == "__main__":
    java_parser = parser()
    parse_tree = java_parser.parse()
    method_node = find_method_declaration_node(parse_tree.root_node)

    paths_vector = []
    paths_vector_index = []
    get_paths(method_node, [], paths_vector)
    get_paths(method_node, [], paths_vector_index, "index")

    positive_paths = [f"{'_'.join([f'({item})' for item in path[:-1]])},{path[-1]}" for path in paths_vector]
    negative_paths = [f"{path[-1]},{'^'.join([f'({item})' for item in reversed(path[:-1])])}" for path in paths_vector]
    
    # 模型提供的输出路径
    model_paths = read_model_paths()
    model_paths_num = len(model_paths)//2
    # 记录每条路径的最大相似，把最大相似的路径序号放进来
    model_paths_ans = []
    # 生成树生成的路径数量
    gen_paths_num = len(positive_paths)

    for i in range(model_paths_num):
        # i 是模型路径匹配序号，需要找出 i 对应的相似度最大的tree-sitter的路径
        # 先是反向路径，再是正向路径
        matchee = model_paths[2 * i]
        highest_ratio = -1
        highest_ratio_order = None
        for j in range(gen_paths_num):
            new_ratio = Levenshtein.ratio(matchee, negative_paths[j])
            if new_ratio > highest_ratio:
                highest_ratio = new_ratio
                highest_ratio_order = j
        model_paths_ans.append(highest_ratio_order)

        # 然后看正向路径
        matchee = model_paths[2 * i + 1]
        highest_ratio = -1
        highest_ratio_order = None
        for j in range(gen_paths_num):
            new_ratio = Levenshtein.ratio(matchee, positive_paths[j])
            if new_ratio > highest_ratio:
                highest_ratio = new_ratio
                highest_ratio_order = j
        model_paths_ans.append(highest_ratio_order)

    # 此时model_paths_ans中按Attention高到低、每组先是反向后是正向的顺序存放
    # 即【Attention最高、反向】【Attention最高、正向】【Attention第二高，反向】……
    tree_dict = {}
    for rank in range(model_paths_num):
        true_rank = model_paths_num-1-rank
        rever_path_ans = model_paths_ans[true_rank*2]
        rever_path = paths_vector_index[rever_path_ans]
        add_label_on_tree(method_node, rever_path, true_rank, tree_dict)

        posi_path_ans = model_paths_ans[true_rank*2+1]
        posi_path = paths_vector_index[posi_path_ans]
        add_label_on_tree(method_node, posi_path, true_rank, tree_dict)

    # 生成json

    gen_json(method_node, 0, tree_dict)
    with open("./java_out.txt", "w+") as f:
        f.write(json)


