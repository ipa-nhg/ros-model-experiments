dependencies=$(rospack depends-indent $1)

declare -A depends_uniq
for d in $dependencies
do 
    depends_uniq[$d]=1
done

for d in ${!depends_uniq[@]}
do
    case $d in catkin|genmsg|cpp_common|std_msgs|genpy|rostime|message_runtime|rosconsole|rosbuild|roscpp_traits|xmlrpcpp|roscpp*|rosgraph_msgs|rosmaster|roslib|message_generation|gencpp|genlisp|rospack|rosunit|rosparam|realtime_tools|gennodejs|rosgraph|rospy|rossservice|ros_environment|topic_tools|pluginlib|rosbag*|geneus|std_srvs|actionlib|*_msgs|*_srvs|rostopic|roslaunch|rosclean|rosout|rviz|cmake*|rqt*|tf|tf2) 
        true
    ;;
  *)
        info=$(roslocate info $d)
        tmp=${info#*uri: }
        repo=${tmp%version*}
        version=${info#*version: }
        if [ -z "$version" ]
        then
            git clone $repo
        else
            git clone $repo --branch $version
        fi
    ;;
    esac
done

cd ..
#all_pkg=$(catkin list --unformatted)
#pkg_blacklist=""
#for pkg in $all_pkg
#do
#    if [[ ! " ${depends_uniq[@]} "  =~ " ${pkg} " ]]
#    then
#        pkg_blacklist+=$pkg";"
#    fi
#done

#cob experiment
touch src/cob_hand/cob_hand_bridge/CATKIN_IGNORE
touch src/rplidar_ros/CATKIN_IGNORE
touch src/cob_control/cob_obstacle_distance/CATKIN_IGNORE
touch src/moveit/moveit_kinematics/CATKIN_IGNORE
#catkin_make_isolated -DCMAKE_EXPORT_COMPILE_COMMANDS=1 -DCMAKE_CXX_COMPILER=/usr/bin/clang++-3.8 -DCATKIN_BLACKLIST_PACKAGES="$pkg_blacklist"
catkin_make_isolated --only-pkg-with-deps $1 -DCMAKE_EXPORT_COMPILE_COMMANDS=1 -DCMAKE_CXX_COMPILER=/usr/bin/clang++-3.8 --merge #(--force-cmake)

mkdir build && touch build/compile_commands.json
cat build_isolated/*/compile_commands.json >> build/compile_commands.json
sed -i -e 's/\]\[/\,/g' build/compile_commands.json

source devel_isolated/setup.bash

roslaunch-dump src/cob_robots/cob_bringup/robots/cob4-10.launch robot:=cob4-10 robot_env:=empty > src/cob_robots/cob_bringup/robots/ 
ros_model_extractor.py --package cob_bringup --name cob4_ros_tool_test.launch --launch --output true
