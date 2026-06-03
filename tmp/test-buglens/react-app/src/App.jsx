export default function App()
{
  const fruitlist = ['apple' , 'orange' , 'grapes' , 'banana'] ;
  return(
    <ul>
      {fruitlist.map(fruit => 
        <li key = {fruit}>{fruit}</li>
      )}
    </ul>
  );
}

