# Define a little parser combinator microlibrary for help parsing the grammars

def none_of(chars):
    def inner(s):
        if s[0] in chars:
            raise ValueError("unexpected " + s[0])
        return (s[1:], s[0])
    return inner

def one_of(chars):
    def inner(s):
        if not s or s[0] not in chars:
            raise ValueError("expected one of " + chars)
        return (s[1:], s[0])
    return inner
   
def series(*parsers):
    def inner(s):
        result = []
        for parser in parsers:
            (s, value) = parser(s)
            result.append(value)
        return (s, result)
    return inner

def alt(*parsers):
    def inner(s):
        exceptions = []
        for parser in parsers:
            try:
                return parser(s)
            except ValueError as e:
                exceptions.append(e)
        raise ValueError("expected one of " + ", ".join(map(str, exceptions)) + " but got " + s[:5])
    return inner

def many(parser):
    def inner(s):
        result = []
        while True:
            try:
                (s, value) = parser(s)
                result.append(value)
            except ValueError:
                break
        return (s, result)
    return inner

def maybe(parser):
    def inner(s):
        try:
            (s, value) = parser(s)
            return (s, value)
        except ValueError:
            return (s, None)
    return inner

def many1(parser):
    def inner(s):
        (s, value) = parser(s)
        (s, values) = many(parser)(s)
        return (s, [value] + values)
    return inner

def intersperse(parser, sep_parser):
    def inner(s):
        try:
            (s, value) = parser(s)
            (s, values) = many(series(sep_parser, parser))(s)
            return (s, [value] + [v for (_, v) in values])
        except ValueError:
            return (s, [])
    return inner

def span_spaces():
    def inner(s):
        (s, _) = many(one_of(" \t"))(s)
        return (s, None)
    return inner

def spaces():
    def inner(s):
        (s, _) = many(one_of(" \t\r\n"))(s)
        return (s, None)
    return inner

def nl():
    return alt(literal("\r\n"), literal("\n"))

def alpha():
    return one_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

def digit():
    return one_of("0123456789")

def literal(string):
    return series(*[one_of(c) for c in string])

# Grammar data structures

class Terminal:
    def __init__(self, value):
        if not isinstance(value, str):
            raise TypeError("Terminal value must be a string")
        self.bytes = [ord(c) for c in value]

    def __eq__(self, other):
        return self.bytes == other.bytes

class NonTerminal:
    def __init__(self, rule_name):
        self.rule_name = rule_name

    def __eq__(self, other):
        return self.rule_name == other.rule_name

class Branch:
    def __init__(self, elements):
        if not isinstance(elements, list):
            raise TypeError("Branch elements must be a list")
        if not all(isinstance(element, (Terminal, NonTerminal)) for element in elements):
            raise TypeError("Branch elements must be a list of Terminals and NonTerminals")
        self.elements = elements

    def __eq__(self, other):
        return self.elements == other.elements

class Rule:
    def __init__(self, rule_name, branches):
        self.rule_name = rule_name
        self.branches = branches

    def __eq__(self, other):
        return self.rule_name == other.rule_name and self.branches == other.branches

class Grammar:
    def __init__(self, rules, main_rule):
        self.rules = rules
        self.main_rule = main_rule

    def add_rule(self, rule):
        if isinstance(rule, str):
            (rem, rule) = parse_rule()(rule)
            if rem:
                raise ValueError("rule had trailing characters: " + rem)

        if rule.rule_name in self.rules:
            if rule != self.rules[rule.rule_name]:
                raise ValueError("rule name collision")
        else:
            self.rules[rule.rule_name] = rule

    def grammar(self):
        def get_rule_names(node, visited=None):
            if visited is None:
                visited = set()
            if isinstance(node, NonTerminal):
                return get_rule_names(self.rules[node.rule_name], visited)
            elif isinstance(node, Branch):
                for element in node.elements:
                    get_rule_names(element, visited)
            elif isinstance(node, Rule):
                if node.rule_name not in visited:
                    visited.add(node.rule_name)
                    for branch in node.branches:
                        get_rule_names(branch, visited)
            return visited

        all_rules = get_rule_names(self.main_rule)
        rule_ids = { rule_name : i for (i, rule_name) in enumerate(all_rules) }
        id = lambda rule: rule_ids[rule.rule_name]

        result = ""
        result += f"{id(self.main_rule)} {len(all_rules)}\n"
        for rule_name in rule_ids:
            rule = self.rules[rule_name]
            result += f"{id(rule)} {len(rule.branches)}\n"
            for branch in rule.branches:
                result += f"{len(branch.elements)}\n"
                for element in branch.elements:
                    if isinstance(element, Terminal):
                        result += f"0 {len(element.bytes)} {' '.join(map(str, element.bytes))}\n"
                    elif isinstance(element, NonTerminal):
                        result += f"1 {id(element)}\n"
                    else:
                        raise TypeError("unsupported element type")
                    
        return result

# Grammar parsing

def rule_char(): 
    return alt(alpha(), digit(), one_of("_-."))

def parse_rule_name():
    def inner(s):
        (s, chars) = many1(rule_char())(s)
        return (s, "".join(chars))
    return inner

def parse_terminal():
    def double_quoted(s):
        (s, _) = literal("\"")(s)
        (s, chars) = many(alt(none_of("\""), literal("\\\"")))(s)
        (s, _) = literal("\"")(s)
        return (s, Terminal("".join(chars)))

    def single_quoted(s):
        (s, _) = literal("'")(s)
        (s, chars) = many(alt(none_of("'"), literal("\\'")))(s)
        (s, _) = literal("'")(s)
        return (s, Terminal("".join(chars)))
    
    return alt(double_quoted, single_quoted)

def parse_non_terminal():
    def inner(s):
        (s, _) = literal("<")(s)
        (s, rule_name) = parse_rule_name()(s)
        (s, _) = literal(">")(s)
        return (s, NonTerminal(rule_name))
    return inner

def parse_element():
    return alt(parse_terminal(), parse_non_terminal())

def parse_branch():
    def inner(s):
        (s, elements) = intersperse(parse_element(), span_spaces())(s)
        return (s, Branch(elements))
    return inner

def parse_rule_body():
    return intersperse(parse_branch(), series(span_spaces(), literal("|"), span_spaces()))

def parse_rule():
    def inner(s):
        (s, rule_name) = parse_rule_name()(s)
        (s, _) = span_spaces()(s)
        (s, _) = literal("=")(s)
        (s, _) = span_spaces()(s)
        (s, branches) = parse_rule_body()(s)
        (s, _) = span_spaces()(s)
        return (s, Rule(rule_name, branches))
    return inner

def grammar():
    def inner(s):
        (s, rules) = intersperse(parse_rule(), nl())(s)
        (s, _) = spaces()(s)
        return (s, rules)
    return inner

def type_char():
    return alt(alpha(), digit(), one_of("_"))

def parse_type_name():
    def inner(s):
        (s, chars) = many1(type_char())(s)
        return (s, "".join(chars))
    return inner

# JSON spec data structures

class JsonType:
    def __eq__(self, other):
        return repr(self) == repr(other)
    
    def __hash__(self):
        return hash(repr(self))
    
    def rule_name(self):
        return f"rule_{abs(hash(repr(self)))}"
    
    def expr_rule_name(self):
        return f"<{self.rule_name()}>"
    
    def visit_types(self):
        yield self

class JsonBoolean(JsonType):
    def __repr__(self):
        return "boolean"
    
    def add_to_grammar(self, grammar, user_types):
        grammar.add_rule(f'{self.rule_name()} = "true" | "false"')
    
class JsonInteger(JsonType):
    def __repr__(self):
        return "integer"
    
    def add_to_grammar(self, grammar, user_types):
        grammar.add_rule(f'{self.rule_name()} = <sign> <digits>')
    
class JsonUnsigned(JsonType):
    def __repr__(self):
        return "unsigned"
    
    def add_to_grammar(self, grammar, user_types):
        grammar.add_rule(f'{self.rule_name()} = <digits>')
    
class JsonFloat(JsonType):
    def __repr__(self):
        return "float"

    def add_to_grammar(self, grammar, user_types):
        grammar.add_rule(f'{self.rule_name()} = <sign> <digits> | <sign> <digits> "." <digits>') 
    
class JsonString(JsonType):
    def __repr__(self):
        return "string"

    def add_to_grammar(self, grammar, user_types):
        grammar.add_rule(f'{self.rule_name()} = ' + '''   '"' <string_chars> '"'    '''.strip())
    
class JsonNull(JsonType):
    def __repr__(self):
        return "null"

    def add_to_grammar(self, grammar, user_types):
        grammar.add_rule(f'{self.rule_name()} = "null"') 
    
class JsonTuple(JsonType):
    def __init__(self, types):
        self.types = types

    def __repr__(self):
        return "[" + ", ".join(map(repr, self.types)) + "]"
    
    def visit_types(self):
        yield from super().visit_types()
        for t in self.types:
            yield from t.visit_types()

    def add_to_grammar(self, grammar, user_types):
        for t in self.types:
            t.add_to_grammar(grammar, user_types)

        rule_body = ' "[" '
        for (i, t) in enumerate(self.types):
            if i > 0:
                rule_body += ' ", " '
            rule_body += f'{self.types[i].expr_rule_name()}'
        rule_body += ' "]" '

        grammar.add_rule(f'{self.rule_name()} = {rule_body}')

class JsonObject(JsonType):
    def __init__(self, fields):
        self.fields = fields

    def __repr__(self):
        return "{" + ", ".join(map(lambda f: f"{f[0]}: {f[1]}", self.fields)) + "}"
    
    def visit_types(self):
        yield from super().visit_types()
        for (_, t) in self.fields:
            yield from t.visit_types()

    def add_to_grammar(self, grammar, user_types):
        for (_, t) in self.fields:
            t.add_to_grammar(grammar, user_types)

        rule_body = ' "{" '
        for (i, (k, t)) in enumerate(self.fields):
            if i > 0:
                rule_body += ' "," '
            rule_body += f"' \"{k}\"'"
            rule_body += f' ": " {t.expr_rule_name()} " "'
        rule_body += ' "}" '

        grammar.add_rule(f'{self.rule_name()} = {rule_body}')

class JsonUnion(JsonType):
    def __init__(self, types):
        types = { repr(t) : t for t in types}
        self.types = sorted(list(types.values()), key=repr)

    def __repr__(self):
        return " | ".join(map(repr, self.types))
    
    def visit_types(self):
        yield from super().visit_types()
        for t in self.types:
            yield from t.visit_types()

    def add_to_grammar(self, grammar, user_types):
        for t in self.types:
            t.add_to_grammar(grammar, user_types)

        rule_body = ''
        for (i, t) in enumerate(self.types):
            if i > 0:
                rule_body += ' | '
            rule_body += f'{t.expr_rule_name()}'

        grammar.add_rule(f'{self.rule_name()} = {rule_body}')

class JsonArray(JsonType):
    def __init__(self, value_type):
        self.value_type = value_type

    def __repr__(self):
        return f"Array<{self.value_type}>"
    
    def visit_types(self):
        yield from super().visit_types()
        yield from self.value_type.visit_types()

    def add_to_grammar(self, grammar, user_types):
        self.value_type.add_to_grammar(grammar, user_types)
        value_rule_name = self.value_type.rule_name()
        value_expr_rule_name = self.value_type.rule_name()
        many_rule_name = f'{value_rule_name}_many'
        many_expr_rule_name = f'<{many_rule_name}>'
        grammar.add_rule(f'{many_rule_name} = {value_expr_rule_name} | {value_expr_rule_name} ", " {many_expr_rule_name}')
        grammar.add_rule(f'{self.rule_name()} = "[" {many_expr_rule_name} "]"')

class JsonUserType(JsonType):
    def __init__(self, type_name):
        self.type_name = type_name

    def __repr__(self):
        return self.type_name
    
    def add_to_grammar(self, grammar, user_types):
        user_type = user_types[self.type_name]
        user_type.add_to_grammar(grammar, user_types)
        grammar.add_rule(f'{self.rule_name()} = {user_type.expr_rule_name()}')

class JsonStringLiteralType(JsonType):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f'"{self.value}"'
    
    def add_to_grammar(self, grammar, user_types):
        grammar.add_rule(f'{self.rule_name()} = "{self.value}"')

class JsonSpec:
    def __init__(self, types):
        self.types = types

    def grammar(self):
        g = Grammar({}, None)
        g.add_rule('nil = ')
        g.add_rule('digit = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"')
        g.add_rule('digits = <digit> | <digit> <digits>')
        g.add_rule('sign = "-" | <nil>')
        g.add_rule('alphanumspace = ' + " | ".join(map(lambda c: f'"{c}"', "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")))
        g.add_rule('escaped_double_quote = \'\\"\'')
        g.add_rule('string_char = <alphanumspace> | <escaped_double_quote>')
        g.add_rule('string_chars = <nil> | <string_char> <string_chars>')

        types_by_name = { n : t for (n, t) in self.types }

        for (_, t) in self.types:
            t.add_to_grammar(g, types_by_name)

        main_type = self.types[-1][1]
        main_type_name = main_type.rule_name()

        g.main_rule = g.rules[main_type_name]

        return g.grammar()

# JSON spec parsing

def parse_boolean_type():
    def inner(s):
        (s, _) = literal("boolean")(s)
        return (s, JsonBoolean())
    return inner

def parse_integer_type():
    def inner(s):
        (s, _) = literal("integer")(s)
        return (s, JsonInteger())
    return inner

def parse_unsigned_type():
    def inner(s):
        (s, _) = literal("unsigned")(s)
        return (s, JsonUnsigned())
    return inner

def parse_float_type():
    def inner(s):
        (s, _) = alt(literal("float"), literal("double"), literal("number"))(s)
        return (s, JsonFloat())
    return inner

def parse_string_type():
    def inner(s):
        (s, _) = literal("string")(s)
        return (s, JsonString())
    return inner

def parse_null_type():
    def inner(s):
        (s, _) = literal("null")(s)
        return (s, JsonNull())
    return inner

def parse_tuple_type():
    def inner(s):
        (s, _) = literal("[")(s)
        (s, types) = intersperse(parse_type_body(), series(spaces(), literal(","), spaces()))(s)
        (s, _) = series(maybe(literal(",")), spaces())(s)
        (s, _) = literal("]")(s)
        return (s, JsonTuple(types))
    return inner

def parse_object_key():
    def inner(s):
        (s, _) = literal('"')(s)
        (s, key) = many1(alt(none_of('"'), literal('\\"')))(s)
        (s, _) = literal('"')(s)
        return (s, "".join(key))
    return inner

def parse_object_field():
    def inner(s):
        (s, key) = parse_object_key()(s)
        (s, _) = series(span_spaces(), literal(":"), span_spaces())(s)
        (s, value) = parse_type_body()(s)
        return (s, (key, value))
    return inner

def parse_object_type():
    def inner(s):
        (s, _) = series(literal("{"), spaces())(s)
        (s, fields) = intersperse(parse_object_field(), series(spaces(), literal(","), spaces()))(s)
        (s, _) = series(maybe(literal(",")), spaces(), literal("}"))(s)
        return (s, JsonObject(fields))
    return inner

def parse_array_type():
    def inner(s):
        (s, _) = literal("Array<")(s)
        (s, value_type) = parse_type_body()(s)
        (s, _) = literal(">")(s)
        return (s, JsonArray(value_type))
    return inner

def parse_user_type():
    def inner(s):
        (s, type_name) = parse_type_name()(s)
        return (s, JsonUserType(type_name))
    return inner

def parse_string_literal_type():
    def inner(s):
        (s, _) = literal('"')(s)
        (s, value) = many1(alt(none_of('"'), literal('\\"')))(s)
        (s, _) = literal('"')(s)
        return (s, JsonStringLiteralType("".join(value)))
    return inner

def parse_single_type_body():
    return alt(
        parse_boolean_type(),
        parse_integer_type(),
        parse_unsigned_type(),
        parse_null_type(),
        parse_float_type(),
        parse_string_type(),
        parse_tuple_type(),
        parse_object_type(),
        parse_array_type(),
        parse_string_literal_type(),
        parse_user_type(),
    )

def parse_type_body():
    def inner(s):
        (s, types) = intersperse(parse_single_type_body(), series(span_spaces(), literal("|"), span_spaces()))(s)
        if len(types) == 1:
            return (s, types[0])
        else:
            return (s, JsonUnion(types))
    return inner

def parse_type_definition():
    def inner(s):
        (s, _) = series(spaces(), literal("type "))(s)
        (s, type_name) = parse_type_name()(s)
        (s, _) = series(spaces(), literal("="), spaces())(s)
        (s, type_body) = parse_type_body()(s)
        (s, _) = series(spaces(), literal(";"))(s)
        return (s, (type_name, type_body))
    return inner

def json_spec(s):
    (s, types) = many1(parse_type_definition())(s)
    (s, _) = spaces()(s)
    if s:
        raise Exception("JSON spec had unparsed trailing characters:\n" + s)
    return JsonSpec(types)

HELP = """

--grammar <path> : parse a full grammar from a file
--grammar <string> : parse a full grammar from a string

The last rule in the grammar is the main rule.

Example grammar:
person = "Bob" | "Alice" | "Charlie"
digit = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
age = digit | digit digit
sentence = person "is" age "years old"

--json <path> : parse a json spec from a file
--json <string> : parse a json spec from a string

The last type declaration in the json spec is the main type.

Example JSON spec:
type FirstNameLastName = [string, string];
type Result = {
    "country": string,
    "population": integer,
    "percent_retired": float,
    "cities": Array<{ "city": string, "is_capital": boolean }>,
    "head_of_state": FirstNameLastName | null,
};

""".strip()

def main():
    import sys
    # modes: parse a full grammar, parse a json spec
    if len(sys.argv) < 3 or sys.argv[1] in ["--help", "-h", "help"]:
        print(HELP)
        sys.exit(1)

    if sys.argv[1] == "--grammar":
        grammar_string = None
        # try to open the file, otherwise interpret the argument as a string
        try:
            with open(sys.argv[2], "r") as f:
                grammar_string = f.read()
        except FileNotFoundError:
            grammar_string = sys.argv[2]

        (s, rules) = grammar()(grammar_string.strip())
        if s:
            print("Grammar had unparsed trailing characters:\n" + s)
            sys.exit(1)
        rules_by_name = { rule.rule_name : rule for rule in rules }
        main_rule = rules[-1]
        print(Grammar(rules_by_name, main_rule).grammar())

    elif sys.argv[1] == "--json":
        json_string = None
        # try to open the file, otherwise interpret the argument as a string
        try:
            with open(sys.argv[2], "r") as f:
                json_string = f.read()
        except FileNotFoundError:
            json_string = sys.argv[2]

        print(json_spec(json_string).grammar())

if __name__ == "__main__":
    main()