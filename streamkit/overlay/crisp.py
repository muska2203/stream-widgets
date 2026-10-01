"""Hard-edged (alpha-cutoff) shaders for chroma key.

The default ursina shaders output smooth alpha gradients at text/texture
edges; those semi-transparent pixels blend with the key color and leave a
halo after the OBS Chroma Key filter. These variants keep the same look but
cut alpha at 0.5 and output fully opaque pixels, so every visible edge is
crisp and keys cleanly.
"""

from ursina import Vec2
from ursina.shader import Shader

CRISP_TEXT = Shader(name="crisp_text", language=Shader.GLSL, vertex='''#version 130

uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uvs;

in vec4 p3d_Color;
out vec4 vertex_color;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uvs = p3d_MultiTexCoord0;
    vertex_color = p3d_Color;
}
''', fragment='''#version 140

uniform sampler2D p3d_Texture0;
in vec2 uvs;
out vec4 frag_color;

in vec4 vertex_color;

void main() {
    if (texture(p3d_Texture0, uvs).a < 0.5) discard;
    frag_color = vec4(vertex_color.rgb, 1.0);
}
''')

CRISP_UNLIT = Shader(name="crisp_unlit", language=Shader.GLSL, vertex='''#version 130

uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uvs;
uniform vec2 texture_scale;
uniform vec2 texture_offset;

in vec4 p3d_Color;
out vec4 vertex_color;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uvs = (p3d_MultiTexCoord0 * texture_scale) + texture_offset;
    vertex_color = p3d_Color;
}
''', fragment='''#version 140

uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
in vec2 uvs;
out vec4 frag_color;

in vec4 vertex_color;

void main() {
    vec4 c = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    if (c.a < 0.5) discard;
    frag_color = vec4(c.rgb, 1.0);
}
''', default_input={
    "texture_scale": Vec2(1, 1),
    "texture_offset": Vec2(0, 0),
})

CRISP_TEXT.compile()
CRISP_UNLIT.compile()
