import React, { useState } from 'react';
import { Form, Button, Alert } from 'react-bootstrap';
import '../styles/LoginPage.css';

type FormErrors = {
  username?: string;
  password?: string;
  server?: string;
};


function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});

  const validateForm = (): FormErrors => {
    const newErrors: FormErrors = {};

    if (!username) newErrors.username = 'Username is required';
    // else if (!/\S+@\S+\.\S+/.test(email)) newErrors.email = 'Email is invalid';
    if (!password) newErrors.password = 'Password is required';
    else if (password.length < 6) newErrors.password = 'Password must be at least 6 characters';
    return newErrors;
  };

  const handleSubmit = async(event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    
    const formErrors = validateForm();
    // if there are validation errors, set them and return
    if (Object.keys(formErrors).length > 0) {
      setErrors(formErrors);
      return;
    } 

    setErrors({});

    try {
    // send login request to backend
    const response = await fetch('/auth/login', {
        method: 'POST',
        headers: {
        'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
        });
        if (!response.ok) {
            throw new Error('Login failed. Please check your credentials.');
        } else {

            const data = await response.json();
            localStorage.setItem('chat_jwt', data.access_token);

            // redirect to home page
            window.location.href = '/home';
        }
    } catch (error) {
        setErrors({ server: 'Invalid username or password' });
    }
  };


  return (
  <div className="login-wrapper">
    <div className="login-form-container">
      <h2 className="login-title">Login</h2>

      {(errors.server || errors.username || errors.password) && (
          <Alert variant="danger">
            {errors.server && <div>{errors.server}</div>}
            {errors.username && <div>{errors.username}</div>}
            {errors.password && <div>{errors.password}</div>}
          </Alert>
        )}

      <Form onSubmit={handleSubmit} className="login-form">
        <Form.Group className="mb-3" controlId="formUsername">
          <Form.Label>Username</Form.Label>
          <Form.Control
            type="text"
            placeholder="Enter username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </Form.Group>

        <Form.Group className="mb-3" controlId="formBasicPassword">
          <Form.Label>Password</Form.Label>
          <Form.Control
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Form.Group>

        <Button variant="primary" type="submit" className="login-button">
          Login
        </Button>
      </Form>
    </div>
  </div>
);
}

export default LoginPage;
