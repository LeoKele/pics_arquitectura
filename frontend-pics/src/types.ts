export interface BBox {
  x_min: number; y_min: number; x_max: number; y_max: number;
}

export interface Falla {
  id: number;
  video_id: number;
  tipo_dano: string;
  confianza: number;
  fecha: string;
  geometria: { coordinates: [number, number] };
  bbox: string | BBox;
  frame_minio_path: string;
  estado_auditoria: 'pendiente' | 'verificado' | 'falso_positivo';
}

export interface VideoEstado {
  id: number;
  estado: string;
}
