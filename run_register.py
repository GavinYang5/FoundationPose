# Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.


from estimater import *
from datareader import *
import argparse


if __name__=='__main__':
  parser = argparse.ArgumentParser()
  code_dir = os.path.dirname(os.path.realpath(__file__))
  parser.add_argument('--mesh_file', type=str, default=f'/home/yang/ExampleData/YKGrasp_dataset/YK_0-3_dataset/YK_3_train_data/mesh/YK_3.ply')
  parser.add_argument('--test_scene_dir', type=str, default=f'/home/yang/ExampleData/YKGrasp_dataset/YK_0-3_dataset/YK_3_train_data')
  parser.add_argument('--est_refine_iter', type=int, default=2)
  parser.add_argument('--track_refine_iter', type=int, default=1)
  parser.add_argument('--debug', type=int, default=2)
  parser.add_argument('--debug_dir', type=str, default=f'{code_dir}/debug_YK_0')
  args = parser.parse_args()

  set_logging_format()
  set_seed(0)

  mesh = trimesh.load(args.mesh_file)
  mesh = mesh.convex_hull
  mesh.fix_normals()
  debug = args.debug
  debug_dir = args.debug_dir
  os.system(f'rm -rf {debug_dir}/* && mkdir -p {debug_dir}/track_vis {debug_dir}/ob_in_cam')

  to_origin, extents = trimesh.bounds.oriented_bounds(mesh)
  bbox = np.stack([-extents/2, extents/2], axis=0).reshape(2,3)

  scorer = ScorePredictor()
  refiner = PoseRefinePredictor()
  glctx = dr.RasterizeCudaContext()
  est = FoundationPose(model_pts=mesh.vertices, model_normals=mesh.vertex_normals, mesh=mesh, scorer=scorer, refiner=refiner, debug_dir=debug_dir, debug=debug, glctx=glctx)
  logging.info("estimator initialization done")

  reader = NoematrixReader(data_dir=args.test_scene_dir, shorter_side=640, zfar=np.inf)
  for i in range(len(reader.color_files)):
    logging.info(f'i:{i}')
    color = reader.get_color(i)
    depth = reader.get_depth(i)
    masks = reader.get_mask(i)
    single_frame_poses = []
    for inst_id, mask in enumerate(masks):
      mask = mask.astype(bool)
      pose = est.register(K=reader.K, rgb=color, depth=depth, ob_mask=mask, iteration=args.est_refine_iter)
      single_frame_poses.append(pose)
      if debug>=3:
        m = mesh.copy()
        m.apply_transform(pose)
        m.export(f'{debug_dir}/model_tf.obj')
        xyz_map = depth2xyzmap(depth, reader.K)
        valid = depth>=0.1
        pcd = toOpen3dCloud(xyz_map[valid], color[valid])
        o3d.io.write_point_cloud(f'{debug_dir}/scene_complete.ply', pcd)
      if debug>=1:
        ori_rgb, ori_depth, camK = reader.get_ori_data(i)
        model_pcd = o3d.io.read_point_cloud(args.mesh_file)
        model_pcd.paint_uniform_color([0.5, 0.5, 0.5])
        model_pcd.transform(pose)
        frame_pcd = create_pcd_from_rgbd(ori_rgb, ori_depth, camK, convert_rgb_to_intensity=False)
        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.1)
        coord.transform(pose)
        o3d.visualization.draw_geometries([frame_pcd, coord, model_pcd])

        center_pose = pose@np.linalg.inv(to_origin)
        vis = draw_posed_3d_box(reader.K, img=color, ob_in_cam=center_pose, bbox=bbox)
        vis = draw_xyz_axis(color, ob_in_cam=center_pose, scale=0.1, K=reader.K, thickness=3, transparency=0, is_input_rgb=True)
        cv2.imshow('1', vis[...,::-1])
        cv2.waitKey(1)
      if debug>=2:
        os.makedirs(f'{reader.data_dir}/track_vis', exist_ok=True)
        imageio.imwrite(f'{reader.data_dir}/track_vis/{reader.id_strs[i]}_{inst_id}.png', vis)

