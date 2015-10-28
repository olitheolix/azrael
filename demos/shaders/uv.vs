#version 330 core

// These buffers were populated by the main program.
layout(location = 0) in vec3 vertexPos;
layout(location = 1) in vec2 uvIndex;

// These values stay constant for the whole mesh.
uniform mat4 projection_matrix;
uniform mat4 model_matrix;
out vec2 UV;

void main(){
  // Extend vertexPosition to a vec4 position vector (hence the value 1),
  // and convert the vertex position into camera coordinates.
  gl_Position =  projection_matrix * model_matrix * vec4(vertexPos, 1);

  // Pass on the UV index to the fragment shader (note that the name
  // UV is a reserved variable in OpenGL and the fragment shader will
  // receive interpolated values, not this exact value written here.
  UV = uvIndex;
}

