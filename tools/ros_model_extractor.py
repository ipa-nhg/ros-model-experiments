#!/usr/bin/env python
#
# Copyright 2019 Fraunhofer Institute for Manufacturing Engineering and Automation (IPA)
#
# Nadia Hammoudeh Garcia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import argparse
import rospkg
from haros.extractor import NodeExtractor
from haros.metamodel import Node, Package, RosName, SourceFile
from haros.launch_parser import LaunchParser, LaunchParserError, NodeTag, RemapTag
from haros.cmake_parser import RosCMakeParser
from bonsai.analysis import CodeQuery
try:
    from bonsai.cpp.clang_parser import CppAstParser
except ImportError:
    CppAstParser = None


class RosExtractor():
  def launch(self):
    self.parse_arg()

    #FIND WORKSPACE: 
    #Fixme: the env variable ROS_PACKAGE_PATH is not the best way to extract the workspace path
    ros_pkg_path = os.environ.get("ROS_PACKAGE_PATH")
    ws = ros_pkg_path[:ros_pkg_path.find("/src:")]

    #BONSAI PARSER
    parser = CppAstParser(workspace = ws)
    parser.set_library_path("/usr/lib/llvm-3.8/lib")
    parser.set_standard_includes("/usr/lib/llvm-3.8/lib/clang/3.8.0/include")
    db_dir = os.path.join(ws, "build")
    if os.path.isfile(os.path.join(db_dir, "compile_commands.json")):
        parser.set_database(db_dir)

    if (self.args.node):
        self.extract_node(self.args.name, self.args.name, self.args.package_name, None, ws, None)
 
    if (self.args.launch):
        pkg = Package(self.args.package_name)
        rospack = rospkg.RosPack()
        pkg.path = rospack.get_path(self.args.package_name)
        relative_path = "launch/"
        for root, dirs, files in os.walk(pkg.path):
            for file in files:
                if file.endswith(self.args.name):
                    relative_path = root.replace("/"+pkg.path,"")
        source = SourceFile(self.args.name,relative_path,pkg)
        pkgs = {pkg.id: pkg}
        launch_parser = LaunchParser(pkgs = pkgs)
        rossystem = ros_system(self.args.name.replace(".launch",""))
        try:
            source.tree = launch_parser.parse(source.path)
            for node in source.tree.children:
                if isinstance(node,NodeTag):
                    name = node.attributes["name"]
                    node_name = node.attributes["type"]
                    node_pkg = node.attributes["pkg"]
                    args = node.attributes["args"]
                    remaps = []
                    for child in node.children:
                        if isinstance(child,RemapTag):
                            remaps.append(child)
                    try:
                        ns = node.attributes["ns"]
                    except:
                        ns=""
                    if node_name == "controller_manager":
                        self.controller_manager_model(name, ns, rossystem, args, remaps)
                    else:
                        self.extract_node(name,node_name,node_pkg,ns,ws,rossystem,remaps)
        except LaunchParserError as e:
            print("Parsing error in %s:\n%s",source.path, str(e))
        system_str = rossystem.save_model()
        if self.args.output:
            print system_str

  def extract_node(self, name, node_name, pkg_name, ns, ws, rossystem, remaps):
        pkg = Package(pkg_name)
        rospack = rospkg.RosPack()
        pkg.path = rospack.get_path(pkg_name)
        roscomponent = None
        #HAROS NODE EXTRACTOR
        analysis = NodeExtractor(pkg, env=dict(os.environ), ws=ws ,node_cache=False, parse_nodes=True)
        node = Node(node_name, pkg, rosname=RosName(node_name))
        srcdir = pkg.path[len(ws):]
        srcdir = os.path.join(ws, srcdir.split(os.sep, 1)[0])
        bindir = os.path.join(ws, "build")
        #HAROS CMAKE PARSER
        parser = RosCMakeParser(srcdir, bindir, pkgs = [pkg])
        model_str = ""
        if os.path.isfile(os.path.join(pkg.path, "CMakeLists.txt")):
            parser.parse(os.path.join(pkg.path, "CMakeLists.txt"))
            for target in parser.executables.itervalues():
                if target.output_name == node_name:
                    for file_in in target.files:
                        full_path = file_in
                        relative_path = full_path.replace(pkg.path+"/","").rpartition("/")[0]
                        file_name = full_path.rsplit('/', 1)[-1]
                        source_file = SourceFile(file_name, relative_path , pkg)
                        node.source_files.append(source_file)
            parser = CppAstParser(workspace = ws)
            node.source_tree = parser.global_scope
            for sf in node.source_files:
                if parser.parse(sf.path) is not None:
                    # ROS MODEL EXTRACT PRIMITIVES
                    rosmodel = ros_model(pkg.name, node_name, node_name)
                    roscomponent = ros_component(name, ns, remaps)
                    self.extract_primitives(node, parser.global_scope, analysis, rosmodel, roscomponent, pkg_name, node_name, node_name)
                    # SAVE ROS MODEL
                    model_str = rosmodel.save_model()
            if rossystem is not None and roscomponent is not None:
                rossystem.add_component(roscomponent)
        if self.args.output:
            print model_str

  def extract_primitives(self, node, gs, analysis, rosmodel, roscomponent, pkg_name, node_name, art_name):
        for call in (CodeQuery(gs).all_calls.where_name("SimpleActionServer").get()):
            if len(call.arguments) > 0:
              name = analysis._extract_action(call)
              action_type = analysis._extract_action_type(call)
              act_server = action_server (name, action_type)
              rosmodel.actsrvs.append(act_server)
              roscomponent.add_interface(name,"actsrvs", pkg_name+"."+art_name+"."+node_name+"."+name)
        for call in (CodeQuery(gs).all_calls.where_name("SimpleActionClient").get()):
            if len(call.arguments) > 0:
              name = analysis._extract_action(call)
              action_type = analysis._extract_action_type(call)
              act_client = action_client(name, action_type)
              rosmodel.actcls.append(act_client)
              roscomponent.add_interface(name,"actcls", str(pkg_name)+"."+str(art_name)+"."+str(node_name)+"."+str(name))
        for call in (CodeQuery(gs).all_calls.where_name("advertise").where_result("ros::Publisher").get()):
            if len(call.arguments) > 1:
                name = analysis._extract_topic(call)
                msg_type = analysis._extract_message_type(call)
                pub = publisher(name, msg_type)
                rosmodel.pubs.append(pub)
                roscomponent.add_interface(name,"pubs", pkg_name+"."+art_name+"."+node_name+"."+name)
        for call in (CodeQuery(gs).all_calls.where_name("subscribe").where_result("ros::Subscriber").get()):
            if len(call.arguments) > 1:
                name = analysis._extract_topic(call)
                msg_type = analysis._extract_message_type(call)
                queue_size = analysis._extract_queue_size(call)
                sub = subscriber(name, msg_type)
                rosmodel.subs.append(sub)
                roscomponent.add_interface(name,"subs", pkg_name+"."+art_name+"."+node_name+"."+name)
        for call in (CodeQuery(gs).all_calls.where_name("advertiseService").where_result("ros::ServiceServer").get()):
            if len(call.arguments) > 1:
                name = analysis._extract_topic(call)
                srv_type = analysis._extract_message_type(call)
                srv_server = service_server(name, srv_type)
                rosmodel.srvsrvs.append(srv_server)
                roscomponent.add_interface(name,"srvsrvs", pkg_name+"."+art_name+"."+node_name+"."+name)
        for call in (CodeQuery(gs).all_calls.where_name("serviceClient").where_result("ros::ServiceClient").get()):
            if len(call.arguments) > 1:
                name = analysis._extract_topic(call)
                srv_type = analysis._extract_message_type(call)
                srv_client = service_client(name, srv_type)
                rosmodel.srvcls.append(srv_client)
                roscomponent.add_interface(name,"srvcls", pkg_name+"."+art_name+"."+node_name+"."+name)

  def controller_manager_model(self,name, ns, rossystem, args, remaps):
    pkg_name= "controller_manager"
    node_name = "controller_manager_"+ns.replace("/","")
    art_name = "controller_manager_"+ns.replace("/","")
    rosmodel = ros_model(pkg_name, node_name, node_name)
    roscomponent = ros_component(node_name, ns, remaps)
    if ("joint_state_controller" in str(args)):
        pub = publisher("joint_states","sensor_msgs/JointState")
        rosmodel.pubs.append(pub)
        roscomponent.add_interface("joint_states","pubs", pkg_name+"."+art_name+"."+node_name+"."+"joint_states")
    if ("twist_controller" in str(args)):
        pub = publisher("twist_controller/wheel_commands","geometry_msgs.Twist")
        rosmodel.pubs.append(pub)
        roscomponent.add_interface("twist_controller/command","pubs", pkg_name+"."+art_name+"."+node_name+"."+"twist_controller/wheel_commands")
    if ("odometry_controller" in str(args)):
        pub = publisher("odometry_controller/odometry","nav_msgs.Odometry")
        rosmodel.pubs.append(pub)
        roscomponent.add_interface("odometry_controller/command","pubs", pkg_name+"."+art_name+"."+node_name+"."+"odometry_controller/odometry")
    rosmodel.save_model()
    if rossystem is not None and roscomponent is not None:
        rossystem.add_component(roscomponent)

  def parse_arg(self):
    parser = argparse.ArgumentParser()
    mutually_exclusive = parser.add_mutually_exclusive_group()
    mutually_exclusive.add_argument('--node', '-n', help="node analyse", action='store_true')
    mutually_exclusive.add_argument('--launch', '-l', help="launch analyse", action='store_true')
    parser.add_argument('--output', help='print the model output')
    parser.add_argument('--package', required=True, dest='package_name')
    parser.add_argument('--name', required=True, dest='name')
    self.args = parser.parse_args()

class ros_model:
  def __init__(self, pkg_name, name, node_name):
    self.package = pkg_name
    self.artifact = name
    self.node = node_name
    self.pubs = []
    self.subs = []
    self.srvsrvs = []
    self.srvcls = []
    self.actsrvs = []
    self.actcls = []
  def save_model(self):
    model_str = "PackageSet { package { \n"
    model_str = model_str+"  CatkinPackage "+self.package+" { "
    model_str = model_str+"artifact {\n    Artifact "+self.artifact+" {\n"
    model_str = model_str+"      node Node { name "+ self.node+"\n"
    if len(self.srvsrvs) > 0:
        model_str = model_str+"        serviceserver {\n"
        count = len(self.srvsrvs)
        for srv in self.srvsrvs:
            model_str = model_str+"          ServiceServer { name '"+str(srv.name)+"' service '"+str(srv.srv_type)+"'}"
            count = count -1
            if count > 0:
                model_str = model_str+",\n"
            else:
                model_str = model_str+"}\n"
    if len(self.pubs) > 0:
        model_str = model_str+"        publisher {\n"
        count = len(self.pubs)
        for pub in self.pubs:
            model_str = model_str+"          Publisher { name '"+str(pub.name)+"' message '"+str(pub.msg_type)+"'}"
            count = count -1
            if count > 0:
                model_str = model_str+",\n"
            else:
                model_str = model_str+"}\n"
    if len(self.subs) > 0:
        model_str = model_str+"        subscriber {\n"
        count = len(self.subs)
        for sub in self.subs:
            model_str = model_str+"          Subscriber { name '"+str(sub.name)+"' message '"+str(sub.msg_type)+"'}"
            count = count -1
            if count > 0:
                model_str = model_str+",\n"
            else:
                model_str = model_str+"}\n"
    if len(self.srvcls) > 0:
        model_str = model_str+"        serviceclient {\n"
        count = len(self.srvcls)
        for srv in self.srvcls:
            model_str = model_str+"          ServiceClient { name '"+str(srv.name)+"' service '"+str(srv.srv_type)+"'}"
            count = count -1
            if count > 0:
                model_str = model_str+",\n"
            else:
                model_str = model_str+"}\n"
    if len(self.actsrvs) > 0:
        model_str = model_str+"        actionserver {\n"
        count = len(self.actsrvs)
        for act in self.actsrvs:
            model_str = model_str+"          ActionServer { name '"+str(act.name)+"' action '"+str(act.action_type)+"'}"
            count = count -1
            if count > 0:
                model_str = model_str+",\n"
            else:
                model_str = model_str+"}\n"
    if len(self.actcls) > 0:
        model_str = model_str+"        actionclient {\n"
        count = len(self.actcls)
        for act in self.actcls:
            model_str = model_str+"          ActionClient { name '"+str(act.name)+"' action '"+str(act.action_type)+"'}"
            count = count -1
            if count > 0:
                model_str = model_str+",\n"
            else:
                model_str = model_str+"}\n"
    model_str = model_str + "}}}}}}"
    text_file = open(self.node+".ros", "w")
    text_file.write(model_str)
    text_file.close()
    return model_str

class publisher:
  def __init__(self, name, msg_type):
    self.name = name
    self.msg_type = msg_type.replace("/",".")

class subscriber:
  def __init__(self, name, msg_type):
    self.name = name
    self.msg_type = msg_type.replace("/",".")

class service_server:
  def __init__(self, name, srv_type):
    self.name = name
    self.srv_type = srv_type.replace("/",".")

class service_client:
  def __init__(self, name, srv_type):
    self.name = name
    self.srv_type = srv_type.replace("/",".")

class action_server:
  def __init__(self, name, action_type):
    self.name = name
    self.action_type = action_type.replace("/",".")

class action_client:
  def __init__(self, name, action_type):
    self.name = name
    self.action_type = action_type.replace("/",".")

class RosInterface:
  def __init__(self, name, ref):
    self.name = name
    self.ref = ref

class ros_component:
  def __init__(self, name, ns, remaps):
    self.name = str(ns)+str(name)
    self.remaps = remaps
    self.ns = ns
    self.pubs = []
    self.subs = []
    self.srvsrvs = []
    self.srvcls = []
    self.actsrvs = []
    self.actcls = []
  def add_interface(self, name, interface_type, ref):
    for remap in self.remaps:
        if remap.attributes["from"] == name:
            name = remap.attributes["to"]
    if interface_type == "pubs":
        self.pubs.append(RosInterface(name,ref))
    if interface_type == "subs":
        self.subs.append(RosInterface(name,ref))
    if interface_type == "srvsrvs":
        self.srvsrvs.append(RosInterface(name,ref))
    if interface_type == "srvcls":
        self.srvcls.append(RosInterface(name,ref))
    if interface_type == "actsrvs":
        self.actsrvs.append(RosInterface(name,ref))
    if interface_type == "actcls":
        self.actcls.append(RosInterface(name,ref))

class ros_system:
  def __init__(self, name):
    self.name = name
    self.components = []

  def add_component(self, component):
    self.components.append(component)

  def save_model(self):
    system_model_str = "RosSystem { Name "+self.name+"\n"
    if len(self.components)>0:
        cout_c = len(self.components)
        system_model_str+="    RosComponents ( \n"
        for comp in self.components:
            pubs = comp.pubs
            subs = comp.subs
            srvsrvs = comp.srvsrvs
            srvcls = comp.srvcls
            actsrvs = comp.actsrvs
            actcls = comp.actcls
            if comp.ns is not None:
                system_model_str+="        ComponentInterface { name '"+str(comp.name)+"' NameSpace '"+str(comp.ns)+"' \n" 
            else:
                system_model_str+="        ComponentInterface { name '"+str(comp.name)+"' \n" 
            if len(pubs) > 0:
                system_model_str+="            RosPublishers{\n"
                count = len(pubs)
                for pub in pubs:
                    if ((pub.name.startswith('/')) or (comp.ns is None)):
                        system_model_str+="                RosPublisher '"+str(pub.name)+"' { RefPublisher '"+str(pub.ref)+"'}"
                    else:
                        system_model_str+="                RosPublisher '"+str(comp.ns+pub.name)+"' { RefPublisher '"+str(pub.ref)+"'}"
                    count = count -1
                    if count > 0:
                        system_model_str+=",\n"
                    else:
                        system_model_str+="}\n"
            if len(subs) > 0:
                system_model_str+="            RosSubscribers{\n"
                count = len(subs)
                for sub in subs:
                    if ((sub.name.startswith('/')) or (comp.ns is None)):
                        system_model_str+="                RosSubscriber '"+str(sub.name)+"' { RefSubscriber '"+str(sub.ref)+"'}"
                    else:
                        system_model_str+="                RosSubscriber '"+str(comp.ns+sub.name)+"' { RefSubscriber '"+str(sub.ref)+"'}"
                    count = count -1
                    if count > 0:
                        system_model_str+=",\n"
                    else:
                        system_model_str+="}\n"
            if len(srvsrvs) > 0:
                system_model_str+="            RosSrvServers{\n"
                count = len(srvsrvs)
                for srv in srvsrvs:
                    if ((srv.name.startswith('/')) or (comp.ns is None)):
                        system_model_str+="                RosServiceServer '"+str(srv.name)+"' { RefServer '"+str(srv.ref)+"'}"
                    else:
                        system_model_str+="                RosServiceServer '"+str(comp.ns+srv.name)+"' { RefServer '"+str(srv.ref)+"'}"
                    count = count -1
                    if count > 0:
                        system_model_str+=",\n"
                    else:
                        system_model_str+="}\n"
            if len(srvcls) > 0:
                system_model_str+="            RosSrvClients{\n"
                count = len(srvcls)
                for srv in srvcls:
                    if ((srv.name.startswith('/')) or (comp.ns is None)):
                        system_model_str+="                RosServiceClient '"+str(srv.name)+"' { RefClient '"+str(srv.ref)+"'}"
                    else:
                        system_model_str+="                RosServiceClient '"+str(comp.ns+srv.name)+"' { RefClient '"+str(srv.ref)+"'}"
                    count = count -1
                    if count > 0:
                        system_model_str+=",\n"
                    else:
                        system_model_str+="}\n"
            if len(actsrvs) > 0:
                system_model_str+="            RosActionServers{\n"
                count = len(actsrvs)
                for act in actsrvs:
                    system_model_str+="                RosActionServer '"+str(act.name)+"' { RefServer '"+str(act.ref)+"'}"
                    count = count -1
                    if count > 0:
                        system_model_str+=",\n"
                    else:
                        system_model_str+="}\n"
            if len(actcls) > 0:
                system_model_str+="            RosActionClients{\n"
                count = len(actcls)
                for act in actcls:
                    system_model_str+="                RosActionClient '"+str(act.name)+"' { RefClient '"+str(act.ref)+"'}"
                    count = count -1
                    if count > 0:
                        system_model_str+=",\n"
                    else:
                        system_model_str+="}\n"
            cout_c = cout_c -1
            if cout_c > 0:
                system_model_str+="},\n"
            else:
                system_model_str+="}\n"
        system_model_str+=")"
    system_model_str+="}"
    text_file = open(self.name+".rossystem", "w")
    text_file.write(system_model_str)
    text_file.close()
    return system_model_str

def main(argv = None):
    extractor = RosExtractor()
    if extractor.launch():
        return 0
    return 1

if __name__== "__main__":
  main()
