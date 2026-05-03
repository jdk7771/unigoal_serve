import cv2
import numpy as np
import torch
import matplotlib.pyplot as plt
import os

def save_image(img, path):
    """Save an RGB image to a path."""
    if img.dtype == np.float32 or img.dtype == np.float64:
        img = (img * 255).astype(np.uint8)
    cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))

def save_depth_map(depth, path, max_depth=10.0):
    """Save a depth map as a color-mapped image."""
    # Normalize depth to 0-255
    depth_norm = np.clip(depth / max_depth, 0, 1)
    depth_vis = (depth_norm * 255).astype(np.uint8)
    depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
    cv2.imwrite(path, depth_color)

def save_mask_overlay(rgb, mask, path, color=(0, 255, 0), alpha=0.5):
    """Save an RGB image with a semi-transparent mask overlay."""
    mask_vis = rgb.copy().astype(np.float32)
    mask_indices = mask > 0
    mask_vis[mask_indices] = mask_vis[mask_indices] * (1 - alpha) + np.array(color) * alpha
    cv2.imwrite(path, cv2.cvtColor(mask_vis.astype(np.uint8), cv2.COLOR_RGB2BGR))

def save_bev_map(bev, path, title=None, cmap='viridis'):
    """Save a BEV map with paper-ready styling."""
    plt.figure(figsize=(10, 10))
    # Standard top-down view: agent is at the bottom center facing 'up'
    # bev[0,0] is bottom-left
    plt.imshow(bev, origin='lower', cmap=cmap)
    if title:
        plt.title(title, fontsize=20)
    plt.axis('off')
    plt.savefig(path, bbox_inches='tight', pad_inches=0.1, dpi=300)
    plt.close()

def save_point_cloud_pcd(points, path):
    """Save a point cloud as a simple PCD file."""
    header = f"""# .PCD v0.7 - Point Cloud Data file format
VERSION 0.7
FIELDS x y z
SIZE 4 4 4
TYPE F F F
COUNT 1 1 1
WIDTH {len(points)}
HEIGHT 1
VIEWPOINT 0 0 0 1 0 0 0
POINTS {len(points)}
DATA ascii
"""
    with open(path, 'w') as f:
        f.write(header)
        for p in points:
            f.write(f"{p[0]} {p[1]} {p[2]}\n")

def visualize_point_cloud(pcd_pts, path, title="Point Cloud"):
    """Visualize a 3D point cloud projected to 2D with height-based coloring."""
    plt.figure(figsize=(10, 10))
    # Using Z (height) for coloring.
    # We project X and Y to the plot.
    scatter = plt.scatter(pcd_pts[:, 0], pcd_pts[:, 1], s=2, c=pcd_pts[:, 2], cmap='jet')
    plt.colorbar(scatter, label='Height (cm)')
    plt.xlabel('X (Right) (cm)', fontsize=15)
    plt.ylabel('Y (Forward) (cm)', fontsize=15)
    if title:
        plt.title(title, fontsize=20)
    plt.axis('equal')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.savefig(path, bbox_inches='tight', dpi=300)
    plt.close()
