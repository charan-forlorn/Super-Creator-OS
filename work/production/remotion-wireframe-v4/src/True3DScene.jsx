import React, {useEffect, useRef, useState} from 'react';
import {continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as THREE from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';

const deg = (value) => (value * Math.PI) / 180;

function makeGeometry(layer) {
  if (layer.asset_kind === 'sphere') return new THREE.SphereGeometry(115, 48, 32);
  if (layer.asset_kind === 'plane') return new THREE.PlaneGeometry(260, 260);
  return new THREE.BoxGeometry(220, 220, 220);
}

function makeMaterial(accent, index) {
  const color = new THREE.Color(accent || '#B7EF83');
  color.offsetHSL((index % 3) * 0.045, 0, index % 2 ? -0.06 : 0.03);
  return new THREE.MeshStandardMaterial({
    color,
    roughness: 0.32 + index * 0.04,
    metalness: 0.18 + index * 0.08,
  });
}

export function True3DScene({scene, accent = '#B7EF83'}) {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const canvasRef = useRef(null);
  const runtimeRef = useRef(null);
  const [handle] = useState(() => delayRender('true-3d-scene'));

  useEffect(() => {
    let disposed = false;
    const canvas = canvasRef.current;
    if (!canvas || !scene) {
      continueRender(handle);
      return () => {};
    }
    try {
      const renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        preserveDrawingBuffer: true,
      });
      renderer.setPixelRatio(1);
      renderer.setSize(width, height, false);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.1;

      const world = new THREE.Scene();
      const cameraSpec = scene.camera || {};
      const camera = new THREE.PerspectiveCamera(
        cameraSpec.fov_deg || 45,
        width / Math.max(1, height),
        1,
        5000,
      );
      camera.position.set(cameraSpec.x || 0, cameraSpec.y || 0, cameraSpec.z || 1000);
      camera.rotation.order = 'XYZ';
      camera.rotation.set(deg(cameraSpec.pitch || 0), deg(cameraSpec.yaw || 0), deg(cameraSpec.roll || 0));

      const ambient = new THREE.AmbientLight(0xffffff, 1.8);
      const key = new THREE.DirectionalLight(0xffffff, 3.2);
      key.position.set(240, -180, 650);
      const rim = new THREE.PointLight(new THREE.Color(accent), 5.0, 1800, 2);
      rim.position.set(-260, 220, 420);
      world.add(ambient, key, rim);

      const root = new THREE.Group();
      world.add(root);
      runtimeRef.current = {renderer, world, camera, root};

      const loader = new GLTFLoader();
      const jobs = (scene.layers || []).map((layer, index) => new Promise((resolve, reject) => {
        const group = new THREE.Group();
        group.position.set((index - ((scene.layers.length - 1) / 2)) * 155, 0, -(layer.z || 0) * 0.45);
        group.scale.setScalar(layer.scale || 1);
        root.add(group);

        if (layer.asset_kind === 'gltf' && layer.asset_id) {
          loader.load(
            staticFile(layer.asset_id),
            (gltf) => {
              const model = gltf.scene;
              model.traverse((node) => {
                if (node.isMesh) {
                  node.castShadow = false;
                  node.receiveShadow = false;
                }
              });
              group.add(model);
              resolve();
            },
            undefined,
            reject,
          );
          return;
        }

        const mesh = new THREE.Mesh(makeGeometry(layer), makeMaterial(accent, index));
        group.add(mesh);
        resolve();
      }));

      Promise.all(jobs).then(() => {
        if (!disposed) {
          renderer.render(world, camera);
          continueRender(handle);
        }
      }).catch((error) => {
        console.error('SCOS_TRUE_3D_LOAD_ERROR', error);
        if (!disposed) {
          continueRender(handle);
        }
      });
    } catch (error) {
      console.error('SCOS_TRUE_3D_INIT_ERROR', error);
      continueRender(handle);
    }

    return () => {
      disposed = true;
      const runtime = runtimeRef.current;
      if (!runtime) return;
      runtime.world.traverse((node) => {
        if (node.geometry?.dispose) node.geometry.dispose();
        if (node.material) {
          const materials = Array.isArray(node.material) ? node.material : [node.material];
          materials.forEach((material) => material.dispose?.());
        }
      });
      runtime.renderer.dispose();
      runtimeRef.current = null;
    };
  }, [scene, width, height, handle, accent]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime || !scene) return;
    const {renderer, world, camera, root} = runtime;
    const time = frame / Math.max(1, fps);
    (scene.layers || []).forEach((layer, index) => {
      const group = root.children[index];
      if (!group) return;
      const p = Number(layer.parallax || 1);
      group.position.y = Math.sin(time * 0.95 + index * 0.7) * 22 * p;
      group.rotation.y = Math.sin(time * 0.7 + index) * 0.11 * p;
      group.rotation.x = Math.cos(time * 0.55 + index * 0.4) * 0.06 * p;
    });
    renderer.render(world, camera);
  }, [frame, fps, scene]);

  return <canvas ref={canvasRef} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', background: 'transparent'}} />;
}