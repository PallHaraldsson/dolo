
from __future__ import division
from dolo.compiler.codegen import to_source

import sys
is_python_3 = sys.version_info >= (3, 0)


def std_date_symbol(s, date):
    if date == 0:
        return '{}_'.format(s)
    elif date <= 0:
        return '{}_m{}_'.format(s, str(-date))
    elif date >= 0:
        return '{}__{}_'.format(s, str(date))


import ast

from ast import Expr, Subscript, Name, Load, Index, Num, UnaryOp, UAdd, Module, Assign, Store, Call, Module, FunctionDef, arguments, Param, ExtSlice, Slice, Ellipsis, Call, Str, keyword, NodeTransformer, Tuple, USub

# def Name(id=id, ctx=None): return ast.arg(arg=id)


class StandardizeDatesSimple(NodeTransformer):

    # replaces calls to variables by time subscripts

    def __init__(self, tvariables):

        self.tvariables = tvariables  # list of variables
        self.variables = [e[0] for e in tvariables]

    def visit_Name(self, node):

        name = node.id
        newname = std_date_symbol(name, 0)
        if (name, 0) in self.tvariables:
            expr = Name(newname, Load())
            return expr
        else:
            return node

    def visit_Call(self, node):

        name = node.func.id
        args = node.args[0]

        if name in self.variables:
            if isinstance(args, UnaryOp):
                # we have s(+1)
                if (isinstance(args.op, UAdd)):
                    args = args.operand
                    date = args.n
                elif (isinstance(args.op, USub)):
                    args = args.operand
                    date = -args.n
                else:
                    raise Exception("Unrecognized subscript.")
            else:
                date = args.n
            newname = std_date_symbol(name, date)
            if newname is not None:
                return Name(newname, Load())

        else:

            # , keywords=node.keywords, starargs=node.starargs, kwargs=node.kwargs)
            return Call(func=node.func, args=[self.visit(e) for e in node.args], keywords=[])


class StandardizeDates(NodeTransformer):

    def __init__(self, symbols, arg_names):

        table = {}
        for a in arg_names:
            t = tuple(a)
            symbol_group = a[0]
            date = a[1]
            an = a[2]

            for b in symbols[symbol_group]:
                index = symbols[symbol_group].index(b)
                table[(b, date)] = (an, date)

        variables = [k[0] for k in table]

        table_symbols = {k: (std_date_symbol(*k)) for k in table.keys()}

        self.table = table
        self.variables = variables  # list of vari
        self.table_symbols = table_symbols

    def visit_Name(self, node):

        name = node.id
        key = (name, 0)
        if key in self.table:
            newname = self.table_symbols[key]
            expr = Name(newname, Load())
            return expr
        else:
            return node

    def visit_Call(self, node):

        name = node.func.id
        args = node.args[0]
        if name in self.variables:
            if isinstance(args, UnaryOp):
                # we have s(+1)
                if (isinstance(args.op, UAdd)):
                    args = args.operand
                    date = args.n
                elif (isinstance(args.op, USub)):
                    args = args.operand
                    date = -args.n
                else:
                    raise Exception("Unrecognized subscript.")
            else:
                date = args.n
            key = (name, date)
            newname = self.table_symbols.get(key)
            if newname is not None:
                return Name(newname, Load())
            else:
                raise Exception(
                    "Symbol {} incorrectly subscripted with date {}.".format(name, date))
        else:

            # , keywords=node.keywords,  kwargs=node.kwargs)
            return Call(func=node.func, args=[self.visit(e) for e in node.args], keywords=[])


class ReplaceName(ast.NodeTransformer):

    # replaces names according to definitions

    def __init__(self, defs):
        self.definitions = defs

    def visit_Name(self, expr):
        if expr.id in self.definitions:
            return self.definitions[expr.id]
        else:
            return expr


def compile_function_ast(expressions, symbols, arg_names, output_names=None, funname='anonymous', return_ast=False, print_code=False, definitions=None, vectorize=True):
    '''
    expressions: list of equations as string
    '''

    from collections import OrderedDict
    table = OrderedDict()

    aa = arg_names

    if output_names is not None:
        aa = arg_names + [output_names]
    for a in aa:

        symbol_group = a[0]
        date = a[1]
        an = a[2]

        for b in symbols[symbol_group]:
            index = symbols[symbol_group].index(b)
            table[(b, date)] = (an, index)

    table_symbols = {k: (std_date_symbol(*k)) for k in table.keys()}

    # standard assignment: i.e. k = s[0]
    index = lambda x: Index(Num(x))

    # declare symbols

    preamble = []

    for k in table:  # order it
        # k : var, date
        arg, pos = table[k]
        std_name = table_symbols[k]
        val = Subscript(value=Name(id=arg, ctx=Load()), slice=index(pos), ctx=Load())
        line = Assign(targets=[Name(id=std_name, ctx=Store())], value=val)
        if arg != 'out':
            preamble.append(line)

    body = []
    std_dates = StandardizeDates(symbols, aa)

    if definitions is not None:
        defs = {e: ast.parse(definitions[e]).body[0].value for e in definitions}

    outs = []
    for i, expr in enumerate(expressions):

        expr = ast.parse(expr).body[0].value
        if definitions is not None:
            expr = ReplaceName(defs).visit(expr)

        rexpr = std_dates.visit(expr)

        rhs = rexpr

        if output_names is not None:
            varname = symbols[output_names[0]][i]
            date = output_names[1]
            out_name = table_symbols[(varname, date)]
        else:
            out_name = 'out_{}'.format(i)

        line = Assign(targets=[Name(id=out_name, ctx=Store())], value=rhs)
        body.append(line)

        line = Assign(targets=[Subscript(value=Name(id='out', ctx=Load()),
                                         slice=index(i), ctx=Store())], value=Name(id=out_name, ctx=Load()))
        body.append(line)

    args = [e[2] for e in arg_names] + ['out']

    if is_python_3:
        from ast import arg
        f = FunctionDef(name=funname, args=arguments(args=[arg(arg=a) for a in args], vararg=None, kwarg=None, kwonlyargs=[], kw_defaults=[], defaults=[]),
                        body=preamble + body, decorator_list=[])
    else:
        f = FunctionDef(name=funname, args=arguments(args=[Name(id=a, ctx=Param()) for a in args], vararg=None, kwarg=None, kwonlyargs=[], kw_defaults=[], defaults=[]),
                        body=preamble + body, decorator_list=[])

    mod = Module(body=[f])
    mod = ast.fix_missing_locations(mod)

    if print_code:

        s = "Function {}".format(mod.body[0].name)
        print("-" * len(s))
        print(s)
        print("-" * len(s))

        print(to_source(mod))

    fun = eval_ast(mod)
    if not vectorize:
        return fun
    else:
        from numba import float64, void, guvectorize
        coredims = [len(symbols[an[0]]) for an in arg_names]
        sig = str.join(',', ['(n_{})'.format(d) for d in coredims])
        n_out = len(expressions)
        if n_out in coredims:
            sig += '->(n_{})'.format(n_out)
            ftylist = float64[:](*([float64[:]] * len(coredims)))
            ftylist = void(*[float64[:]] * (len(coredims) + 1))
        else:
            sig += ',(n_{})'.format(n_out)
            ftylist = void(*[float64[:]] * (len(coredims) + 1))
        gufun = guvectorize([ftylist], sig)(fun)
        return gufun


def eval_ast(mod):

    context = {}

    context['division'] = division  # THAT seems strange !

    import numpy

    context['inf'] = numpy.inf
    context['maximum'] = numpy.maximum
    context['minimum'] = numpy.minimum

    context['exp'] = numpy.exp
    context['log'] = numpy.log
    context['sin'] = numpy.sin
    context['cos'] = numpy.cos

    context['abs'] = numpy.abs

    name = mod.body[0].name
    mod = ast.fix_missing_locations(mod)
    # print( ast.dump(mod) )
    code = compile(mod, '<string>', 'exec')
    exec(code, context, context)
    fun = context[name]
    return fun


def test_compile_allocating():
    from collections import OrderedDict
    eq = ['(a + b*exp(p1))', 'p2*a+b']
    symtypes = [
        ['states', 0, 'x'],
        ['parameters', 0, 'p']
    ]
    symbols = OrderedDict([('states', ['a', 'b']),
                           ('parameters', ['p1', 'p2'])
                           ])
    gufun = compile_function_ast(eq, symbols, symtypes, data_order=None)
    n_out = len(eq)

    import numpy
    N = 100000
    vecs = [numpy.zeros((N, len(e))) for e in symbols.values()]
    out = numpy.zeros((N, n_out))
    gufun(*(vecs + [out]))


def test_compile_non_allocating():
    from collections import OrderedDict
    eq = ['(a + b*exp(p1))', 'p2*a+b', 'a+p1']
    symtypes = [
        ['states', 0, 'x'],
        ['parameters', 0, 'p']
    ]
    symbols = OrderedDict([('states', ['a', 'b']),
                           ('parameters', ['p1', 'p2'])
                           ])
    gufun = compile_function_ast(eq, symbols, symtypes, use_numexpr=False,
                                 data_order=None, vectorize=True)
    n_out = len(eq)

    import numpy
    N = 100000
    vecs = [numpy.zeros((N, len(e))) for e in symbols.values()]
    out = numpy.zeros((N, n_out))
    gufun(*(vecs + [out]))
    d = {}
    try:
        allocated = gufun(*vecs)
    except Exception as e:
        d['error'] = e
    if len(d) == 0:
        raise Exception("Frozen dimensions may have landed in numba ! Check.")
    # assert(abs(out-allocated).max()<1e-8)

if __name__ == "__main__":
    test_compile_allocating()
    test_compile_non_allocating()
    print("Done")
