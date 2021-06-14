import {createApp} from 'vue';
import App from './App.vue';

export default function(props) {
  const app = createApp(App, props).mount('#app');
  return app;
}
