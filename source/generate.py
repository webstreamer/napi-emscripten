import os
import re
import template
import json

func_pattern = 'select_overload<(?P<return_type>.*)[(](?P<args_list>.*)[)].*>[(][&](?P<fun_name>((?!,).)*)[)(.*)]'


class Gen:
    def __init__(self, target, supplement):
        self.target = target
        try:
            portion = os.path.splitext(target)
            with open(portion[0] + '.json', 'r') as f:
                self.supplemental_file_fp = f
                self.supplemental_file = json.loads(f.read())
        except:
            self.supplemental_file_fp = None
            self.supplemental_file = None

        self.supplement = supplement
        self.base_path = os.path.dirname(os.path.realpath(target))

        self.classes = {}
        self.value_objects = {}
        self.pattern = func_pattern
        self.register_content = ''
        self.napi_declaration = ''

    def genfile_start(self):
        if not os.path.exists(os.path.join(self.base_path, 'plugin')):
            os.mkdir(os.path.join(self.base_path, 'plugin'))

        self.output_cxx = os.path.join(self.base_path, 'plugin/binding.cc')
        self.output_cxx_fp = open(self.output_cxx, 'w+')

        (shotname, extension) = os.path.splitext(os.path.basename(os.path.realpath(self.target)))
        self.output_js = os.path.join(self.base_path, 'plugin/%s.js' % shotname)
        self.output_js_fp = open(self.output_js, 'w+')

        #########################################################################
        # node-gyp
        # self.generate_gyp()
        # fixed function and macro
        supplement = ''
        for content in self.supplement:
            supplement += (content + '\n')
        self.output_cxx_fp.write(template.bind_cxx_fixed % (supplement, self.register_content))

        # namespace
        self.generate_namespace()

        napi_init_declaration = ''
        napi_create_declaration = ''

        # value_objects
        for instance in self.value_objects.values():
            # class declaration
            (napi_fun, napi_property) = self.generate_class_declaration(instance)
            # constructor implementation
            self.generate_constructor(instance)
            # property implementation
            self.generate_prop(instance)
            # napi declaration
            self.generate_napi_class_declaration(instance, napi_fun, napi_property)

            napi_init_declaration += '    %s::Init(env, exports);\n' % instance['class_name']
            napi_create_declaration += '        NAPI_DECLARE_METHOD("createObject", %s::CreateObject),\n' % instance[
                'class_name']

        # class
        for instance in self.classes.values():
            # class declaration
            (napi_fun, napi_property) = self.generate_class_declaration(instance)
            # constructor implementation
            self.generate_constructor(instance)
            # function implementation
            self.generate_function(instance)
            # property implementation
            self.generate_prop(instance)
            # class function implementation
            self.generate_class_function(instance)
            # napi declaration
            self.generate_napi_class_declaration(instance, napi_fun, napi_property)

            napi_init_declaration += '    %s::Init(env, exports);\n' % instance['class_name']
            napi_create_declaration += '        NAPI_DECLARE_METHOD("createObject", %s::CreateObject),\n' % instance[
                'class_name']

        # constant
        if self.constants:
            self.napi_declaration += '        // constant\n'
            for constant in self.constants:
                self.napi_declaration += '        {"%s", nullptr, nullptr, %s, nullptr, 0, napi_default, 0},\n' % (
                    constant.jsval, 'get_constant_' + constant.jsval)
                self.output_cxx_fp.write(template.constant_func % ('get_constant_' + constant.jsval, constant.cxxval))

        # napi declaration
        self.output_cxx_fp.write(template.napi_init.substitute(init=napi_init_declaration,
                                                               declaration=self.napi_declaration,
                                                               create_object=napi_create_declaration))

    def genfile_end(self):
        self.output_cxx_fp.close()
        self.output_js_fp.close()
        if not self.supplemental_file_fp == None:
            self.supplemental_file_fp.close()

    def generate_gyp(self):
        self.output_gyp = os.path.join(self.base_path, 'plugin/binding.gyp')
        self.output_gyp_fp = open(self.output_gyp, 'w+')
        self.output_gyp_fp.write(template.bind_gyp %
                                 (os.path.relpath(self.output_cxx,
                                                  start=os.path.dirname(self.output_gyp)),
                                  os.path.relpath(self.target,
                                                  start=os.path.dirname(self.output_gyp))))
        self.output_gyp_fp.close()

    def generate_namespace(self):
        self.output_cxx_fp.write('namespace %s {\n\n' % self.namespace)
        if self.supplemental_file and 'template' in self.supplemental_file:
            for template_fun in self.supplemental_file['template']:
                self.output_cxx_fp.write('\t' + template_fun + '\n')
        for meta_info in self.classes.values():
            for item in [meta_info['constructors'], meta_info['functions'], meta_info['properties'], meta_info['class_functions']]:
                for overload_fun in item.values():
                    for spec_fun in overload_fun:
                        if not spec_fun == None and\
                                not spec_fun[3] == None and\
                                not spec_fun[2] == None and\
                                not '<' in spec_fun[2]:
                            self.output_cxx_fp.write('\t' + 'extern %s %s(%s);\n' % (
                                spec_fun[0],
                                spec_fun[2].split('::')[1],
                                spec_fun[3]))
        for meta_info in self.value_objects.values():
            for item in [meta_info['properties']]:
                for overload_fun in item.values():
                    for spec_fun in overload_fun:
                        if not spec_fun == None and\
                                not spec_fun[3] == None and\
                                not spec_fun[2] == None and\
                                not '<' in spec_fun[2]:
                            self.output_cxx_fp.write('\t' + 'extern %s %s(%s);\n' % (
                                spec_fun[0],
                                spec_fun[2].split('::')[1],
                                spec_fun[3]))

        self.output_cxx_fp.write('\n}  // namespace binding_utils\nusing namespace binding_utils;\n')

    def parse_func_line(self, line, cxx_type, bool_static=False):
        if line == None:
            return None
        searchObj = re.search(self.pattern, line)
        if searchObj:
            return_type = searchObj.group('return_type')
            args_list = searchObj.group('args_list').split(', ')
            fun_name = searchObj.group('fun_name')
            args_real = None
            if not cxx_type in fun_name:
                if not bool_static:
                    del args_list[0]
                self.namespace = fun_name.split('::')[0]
                args_real = searchObj.group('args_list')
            if args_list == ['']:
                args_list = []
            return (return_type, args_list, fun_name, args_real)
        # only for raw property(public, no function)
        return (line.split(',')[0], [], None, line.split(',')[1])

    def parse_class(self, classes):
        for obj in classes:
            meta_info = {}

            meta_info['cxxtype'] = obj.cxxtype
            meta_info['jstype'] = obj.jstype
            meta_info['class_name'] = 'class_' + obj.jstype

            constructors = self.parse_constructor(obj)
            functions = self.parse_function(obj)
            properties = self.parse_property(obj)
            class_function = self.parse_class_function(obj)

            meta_info['constructors'] = constructors
            meta_info['functions'] = functions
            meta_info['properties'] = properties
            meta_info['class_functions'] = class_function

            self.classes[obj.jstype] = meta_info

            # print '=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~= start'
            # print self.classes[obj.jstype].values()
            # print '=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~='

        self.register_content += template.register_class

    def parse_constructor(self, obj):
        result = {'constructor': []}
        for constructor in obj.constructors:
            # print 'constructor arg types: %s\n' % constructor.cxxargtypes
            # print 'constructor cxxparams: %s\n' % constructor.cxxparams
            if constructor.cxxargtypes == None:
                fun_name = constructor.cxxparams.split(',')[0]
                if 'select_over' not in fun_name:
                    fun_name = self.supplemental_file[fun_name].encode("utf-8")
                searchObj = re.search(self.pattern, fun_name)
                if searchObj:
                    args_list = searchObj.group('args_list').split(', ')
                    if args_list == ['']:
                        args_list = []
                    result['constructor'].append(('%s *' % obj.cxxtype,
                                                  searchObj.group('args_list').split(', '),
                                                  searchObj.group('fun_name'),
                                                  searchObj.group('args_list')))
            else:
                args_list = constructor.cxxargtypes.split(', ')
                if args_list == ['']:
                    args_list = []
                result['constructor'].append(('%s *' % obj.cxxtype,
                                              args_list,
                                              'new %s' % obj.cxxtype,
                                              None))

        print '===========constructors=========='
        print result
        print ''
        return result

    def parse_function(self, obj):
        result = {}
        for function in obj.functions.items():
            js_method = function[0]
            result[js_method] = []
            for spec_fun in function[1]:
                fun_name = spec_fun[0]
                if 'select_over' not in fun_name:
                    fun_name = self.supplemental_file[fun_name].encode("utf-8")
                detail = self.parse_func_line(fun_name, obj.cxxtype)
                result[js_method].append(detail)
        print '===========functions=========='
        print result
        print ''
        return result

    def parse_property(self, obj):
        result = {}
        for prop in obj.properties.items():
            js_method = prop[0]
            result[js_method] = []
            prop_function = prop[1][0][0]
            if ',' in prop_function:
                getter = prop_function.split(',')[0]
                if 'select_over' not in getter:
                    getter = self.supplemental_file[getter].encode("utf-8")
                setter = prop_function.split(',')[1]
                if 'select_over' not in setter:
                    setter = self.supplemental_file[setter].encode("utf-8")
            else:
                getter = prop_function
                if 'select_over' not in getter:
                    getter = self.supplemental_file[getter].encode("utf-8")
                setter = None

            result[js_method].append(self.parse_func_line(getter, obj.cxxtype))
            result[js_method].append(self.parse_func_line(setter, obj.cxxtype))

        print '===========properties=========='
        print result
        print ''
        return result

    def parse_class_function(self, obj):
        result = {}
        for static_func in obj.class_functions.items():
            # print static_func
            js_method = static_func[0]
            result[js_method] = []
            for spec_fun in static_func[1]:
                detail = self.parse_func_line(spec_fun[0], obj.cxxtype, True)
                result[js_method].append(detail)

        print '===========class functions=========='
        print result
        print ''
        return result

    def parse_arg_type(self, instance, arg):
        if arg == 'int' or arg == 'intptr_t' or arg == 'size_t':
            return template.args_int
        if arg == 'double' or arg == 'float':
            return template.args_double
        if 'string' in arg:
            return template.args_string

        cxx_type = instance['cxxtype'].split('::')
        if cxx_type[-1] in arg:
            return template.args_cxxtype % (instance['class_name'],
                                            instance['cxxtype'])
        searchObj = re.search('(const)\s*(.*)(&)', arg)
        if searchObj:
            arg = searchObj.group(2)
        
        for obj in self.value_objects.values():
            # if arg.split('::')[-1] =='Rect':
            #     print '~~~~~~~~~~~'
            #     print obj['cxxtype'].split('::')[-1]
            #     print '~~~~~~~~~~~'
            if arg.split('::')[-1]==obj['jstype'].split('::')[-1]:
                return template.args_obj % (obj['class_name'], obj['class_name'])

        # return template.args_obj % (arg, arg)
        print arg

        return '\"parse_arg_type not supported type\"\n'

    def parse_return_type(self, instance, arg):
        if arg == 'void':
            return template.return_void
        if arg == 'bool':
            return template.return_bool
        if arg in ['int', 'intptr_t', 'size_t', 'int&', 'short', 'short&', 'char', 'char&']:
            return template.return_int
        if arg in ['unsigned int', 'unsigned int&', 'unsigned short', 'unsigned short&', 'unsgined char', 'unsigned char&']:
            return template.return_uint
        if arg in ['float', 'float&', 'double', 'double&']:
            return template.return_double
        if arg == 'std::string':
            return template.return_string

        cxx_type = instance['cxxtype'].split('::')[-1]

        if cxx_type in arg:
            # return same class type
            return template.return_cxxtype % ('', instance['class_name'])
        else:
            # return other object type
            for obj in self.value_objects.values():
                if obj['cxxtype'] == arg:
                    return template.return_cxxtype % (obj['class_name'] + '::',
                                                      obj['class_name'])
        print '---------'
        print arg
        # return template.return_void
        return '\"parse_return_type not supported type\"\n'

    def generate_class_declaration(self, instance):
        napi_fun = ''
        declare_fun = '    // function\n'
        if 'functions' in instance:
            for fun_name in instance['functions'].keys():
                napi_fun += '        NAPI_DECLARE_METHOD("{0}", {0}),\n'.format(fun_name)
                declare_fun += '    static napi_value %s(napi_env env, napi_callback_info info);\n' % fun_name

        napi_property = ''
        declare_property = '    // property\n'
        if 'properties' in instance:
            for prop in instance['properties'].items():
                prop_name = prop[0]
                getter = 'get%s' % prop_name
                declare_property += '    static napi_value %s(napi_env env, napi_callback_info info);\n' % getter
                if not prop[1][1] == None:
                    setter = 'set%s' % prop_name
                    declare_property += '    static napi_value %s(napi_env env, napi_callback_info info);\n' % setter
                else:
                    setter = 'nullptr'
                napi_property += '        {"%s", nullptr, nullptr, %s, %s, 0, napi_default, 0},\n' % (prop_name,
                                                                                                      getter,
                                                                                                      setter)

        declare_static_function = '    // static_function\n'
        if 'class_functions' in instance:
            for fun_name in instance['class_functions'].keys():
                declare_static_function += '    static napi_value %s(napi_env env, napi_callback_info info);\n' % fun_name
                self.napi_declaration += '        NAPI_DECLARE_METHOD("{0}", {1}::{0}),\n'.format(fun_name,
                                                                                                  instance['class_name'])

        self.output_cxx_fp.write(template.class_declaration.substitute(name=instance['class_name'],
                                                                       type=instance['cxxtype'],
                                                                       jstype=instance['jstype'],
                                                                       function=declare_fun,
                                                                       property=declare_property,
                                                                       class_function=declare_static_function))
        return (napi_fun, napi_property)

    def generate_napi_class_declaration(self, instance, napi_fun, napi_property):
        self.output_cxx_fp.write(template.fixed_class_function.substitute(name=instance['class_name'],
                                                                          type=instance['cxxtype'],
                                                                          jstype=instance['jstype'],
                                                                          declare_function=napi_fun,
                                                                          declare_property=napi_property))

    def generate_constructor(self, instance):
        self.output_cxx_fp.write('/*-------------------  constructor  -------------------*/\n')
        self.output_cxx_fp.write(template.constructor_func_start.substitute(name=instance['class_name'],
                                                                            type=instance['cxxtype']))
        for list_value in instance['constructors'].values():
            for cons_fun in list_value:
                self.output_cxx_fp.write('        case %d: {\n' % len(cons_fun[1]))

                argc = 0
                args = ''
                for i in range(len(cons_fun[1])):
                    arg_type = cons_fun[1][i]
                    # print arg_type
                    self.output_cxx_fp.write(self.parse_arg_type(instance, arg_type).format(i))
                    argc += 1
                    args += 'arg{0}'.format(i)
                    if not i == len(cons_fun[1]) - 1:
                        args += ', '
                self.output_cxx_fp.write('            p = {0}({1});\n'.format(cons_fun[2], args))

                self.output_cxx_fp.write('        } break;\n')

        self.output_cxx_fp.write(template.constructor_func_end)

    def generate_function(self, instance):
        def detail(fun_name, args):
            if 'operator()' in fun_name:
                self.output_cxx_fp.write('\n            return (*obj)({0});\n'.format(args))
            elif not instance['cxxtype'] in fun_name:
                if args:
                    self.output_cxx_fp.write('\n            return {0}(*obj, {1});\n'.format(fun_name, args))
                else:
                    self.output_cxx_fp.write('\n            return {0}(*obj);\n'.format(fun_name))
            else:
                self.output_cxx_fp.write('\n            return obj->{0}({1});\n'.format(fun_name, args))

        self.output_cxx_fp.write('/*-------------------  function  -------------------*/\n')
        self.generate_function_detail(instance, instance['functions'], detail)

    def generate_function_detail(self, instance, functions, func_detail):
        for overload_fun in functions.items():
            fun_name = overload_fun[0]
            return_type = overload_fun[1][0][0]
            self.output_cxx_fp.write(template.function_datail_start % (return_type,
                                                                       fun_name,
                                                                       instance['cxxtype']))
            for spec_fun in overload_fun[1]:
                self.output_cxx_fp.write('        case %d: {\n' % len(spec_fun[1]))

                argc = 0
                args = ''
                arg_list = spec_fun[1]
                for i in range(len(arg_list)):
                    arg_type = arg_list[i]
                    self.output_cxx_fp.write(self.parse_arg_type(instance, arg_type).format(i))
                    argc += 1
                    args += 'arg{0}'.format(i)
                    if not i == len(arg_list) - 1:
                        args += ', '

                fun_name = spec_fun[2]

                func_detail(fun_name, args)

                self.output_cxx_fp.write('        } break;\n')

            self.output_cxx_fp.write(template.function_datail_end)

            if return_type == 'void':
                return_res = ''
            else:
                return_res = '%s res = ' % return_type
            return_val = self.parse_return_type(instance, return_type)
            self.output_cxx_fp.write(template.func_template.substitute(name=instance['class_name'],
                                                                       fun_name=overload_fun[0],
                                                                       type=instance['cxxtype'],
                                                                       return_res=return_res,
                                                                       return_val=return_val))

    def generate_prop(self, instance):
        self.output_cxx_fp.write('/*-------------------  property  -------------------*/\n')
        for prop in instance['properties'].items():
            # getter
            if prop[1][0][2] == None:
                res = self.parse_getter_type(prop[1][0][0], 'target->%s' % prop[1][0][3])
            elif instance['cxxtype'] in prop[1][0][2]:
                res = self.parse_getter_type(prop[1][0][0], 'target->%s()' % prop[1][0][2])
            else:
                res = self.parse_getter_type(prop[1][0][0], '%s(*target)' % prop[1][0][2])

            self.output_cxx_fp.write(template.prop_getter.substitute(fun_name='get%s' % prop[0],
                                                                     name=instance['class_name'],
                                                                     type=instance['cxxtype'],
                                                                     return_fun=res))
            # setter
            if not prop[1][1] == None:
                res = self.parse_setter_type(prop[1][0][0])
                print instance['cxxtype']
                print prop[1][1]
                if instance['cxxtype'] in prop[1][1][2]:
                    fun = '    target->%s(value);' % prop[1][1][2]
                else:
                    fun = '    %s(*target, value);' % prop[1][1][2]

                self.output_cxx_fp.write(template.prop_setter.substitute(fun_name='set%s' % prop[0],
                                                                         name=instance['class_name'],
                                                                         type=instance['cxxtype'],
                                                                         res=res,
                                                                         fun=fun))

    def parse_getter_type(self, arg, fun):
        if arg == 'int' or arg == 'intptr_t':
            return template.getter_int % (arg, fun)
        return template.getter_obj % (arg, fun)
        return '\"parse_getter_type not supported type\"\n'

    def parse_setter_type(self, arg):
        if arg == 'int' or arg == 'intptr_t':
            return template.setter_int
        if 'string' in arg:
            return template.setter_string
        return '\"parse_setter_type not supported type\"\n'

    def generate_class_function(self, instance):
        def detail(fun_name, args):
            if not instance['cxxtype'] in fun_name:
                self.output_cxx_fp.write('\n            return {0}({1});\n'.format(fun_name, args))
            else:
                self.output_cxx_fp.write('\n            return {0}({1});\n'.format(fun_name, args))

        self.output_cxx_fp.write('/*-------------------  class function  -------------------*/\n')
        self.generate_function_detail(instance, instance['class_functions'], detail)

    # -------------------constant---------------------------
    def parse_constant(self, constants):
        self.register_content += template.register_constant
        self.constants = constants

    # -------------------objects----------------------------
    def parse_objects(self, objects):
        self.register_content += template.register_object
        for obj in objects:
            # if not obj.jstype == 'Size':
            #     continue
            self.value_objects[obj.jstype] = {'jstype': obj.jstype,
                                              'cxxtype': obj.cxxtype,
                                              'class_name': 'object_' + obj.jstype,
                                              'constructors': {'constructor': [(obj.cxxtype + ' *',
                                                                                [],
                                                                                'new ' + obj.cxxtype,
                                                                                None)]},
                                              'properties': {}}

            properties = self.value_objects[obj.jstype]['properties']
            for field in obj.field_arr:
                prop_name = field[0]
                properties[prop_name] = []
                getter = field[1]
                setter = field[2]
                if 'select_over' not in getter:
                    getter = self.supplemental_file[getter].encode("utf-8")
                if not setter == None:
                    if 'select_over' not in setter:
                        setter = self.supplemental_file[setter].encode("utf-8")

                properties[prop_name].append(self.parse_func_line(getter, obj.cxxtype))
                properties[prop_name].append(self.parse_func_line(setter, obj.cxxtype))
            # if obj.jstype == 'Exception':
            #     print self.value_objects[obj.jstype]
            # print self.value_objects[obj.jstype]
            # print obj.jstype
            # print obj.cxxtype
            # print obj.field_arr
        print '===========objects=========='
        # print self.value_objects.values()