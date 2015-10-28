#version 330

// Input vertex data, different for all executions of this shader.
layout(location = 0) in vec3 position;
layout(location = 1) in vec4 vertexColor;

// Values that stay constant for the whole mesh.
uniform mat4 projection_matrix;
uniform mat4 model_matrix;
out vec4 fragmentColor;

void main(){
  // Extend vertexPosition to a vec4 position vector (hence the value 1),
  // and convert the vertex position into camera coordinates.
  gl_Position =  projection_matrix * model_matrix * vec4(position, 1);
  //gl_Position =  vec4(position, 1);

  // Pass vertex color to fragment shader.
  fragmentColor = vertexColor;
}

